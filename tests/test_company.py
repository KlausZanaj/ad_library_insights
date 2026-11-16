"""Company research end to end, offline: name lookup, page ads, reach of the top ads, media.

The browser is replaced by saved responses: a results page, the search-box
suggestions and detail views, all captured from real pages.
"""
import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from ad_library_insights import records, report, server, service
from ad_library_insights.browser import PageSnapshot
from ad_library_insights.client import AdLibraryClient, build_page_url
from ad_library_insights.media import MediaStore, save_ad_media
from ad_library_insights.storage import DiskCache, Throttle

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = date(2026, 11, 13)
PAGE_ID = "325635760632130"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Studio:
    """A client whose page loads, suggestions, detail views and downloads are all scripted."""

    def __init__(self, tmp_path, suggestions="typeahead_pages.json", detail="ad_details_eu_many_countries.json"):
        self.now = 1_000_000.0
        self.sleeps, self.renders, self.lookups, self.sessions, self.opened, self.downloads = [], [], [], [], [], []
        self._suggestions = fixture(suggestions) if suggestions else {"data": {}}
        self._detail = fixture(detail)
        clock = lambda: self.now
        self.media = MediaStore(tmp_path / "media", fetcher=self._download)
        self.client = AdLibraryClient(
            cache=DiskCache(tmp_path / "cache", clock=clock),
            throttle=Throttle(tmp_path / "throttle.json", min_interval=20, clock=clock),
            renderer=self._render, suggester=self._suggest, session_factory=self._session,
            sleep=self._sleep, jitter=lambda: 0.0, clock=clock, media=self.media)

    async def _sleep(self, seconds):
        self.sleeps.append(round(seconds, 2))
        self.now += seconds

    async def _render(self, url, wait_seconds, scroll_rounds):
        self.renders.append(url)
        connection = records.connection_from_text((FIXTURES / "search_results_page.json").read_text("utf-8"))
        return PageSnapshot(url=url, status_code=403, page_text="~190 results",
                            edges=connection["edges"], total_count=connection["count"])

    async def _suggest(self, name, country):
        self.lookups.append((name, country))
        return self._suggestions

    def _download(self, url):
        self.downloads.append(url)
        return b"\xff\xd8 picture", "image/jpeg"

    def _session(self, url, scroll_rounds=40):
        studio = self

        class Session:
            async def __aenter__(self):
                studio.sessions.append(url)
                return self

            async def __aexit__(self, *exc):
                return None

            async def open(self, library_id):
                studio.opened.append(library_id)
                studio.now += 0.4
                return studio._detail

            async def frames(self, video_url, stem):
                paths = [Path(f"{stem}_{n}.jpg") for n in (1, 2, 3)]
                for path in paths:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"frame")
                return [str(p) for p in paths]

        return Session()

    def run(self, coroutine):
        return asyncio.run(coroutine)


def test_page_url_is_built_from_the_page_id():
    url = build_page_url(PAGE_ID, "it")
    assert "view_all_page_id=325635760632130" in url and "search_type=page" in url and "country=IT" in url
    with pytest.raises(ValueError):
        build_page_url("kingshot", "IT")


def test_name_lookup_lists_pages_and_marks_the_likeliest(tmp_path):
    studio = Studio(tmp_path)
    found = studio.run(service.find_pages(studio.client, "zalando", "it"))
    assert found["ok"] and len(found["pages"]) == 15
    assert found["pages"][0]["followers"] >= found["pages"][1]["followers"]
    assert found["suggested_page_id"] == "365604620536"
    studio.run(service.find_pages(studio.client, "Zalando", "IT"))
    assert studio.lookups == [("zalando", "IT")]               # second lookup came from the cache


def test_several_matching_pages_must_be_chosen_before_anything_is_loaded(tmp_path):
    studio = Studio(tmp_path)
    result = studio.run(service.research_company(studio.client, "IT", name="Zalando"))
    assert result["outcome"] == "choose_page" and not result["ok"]
    assert len(result["pages"]) == 15 and result["suggested_page_id"] == "365604620536"
    assert studio.renders == []


def test_unknown_name_reports_no_page(tmp_path):
    studio = Studio(tmp_path, suggestions=None)
    result = studio.run(service.research_company(studio.client, "IT", name="Nobody Here"))
    assert result["outcome"] == "no_page" and "Nobody Here" in result["note"]


def test_company_ads_come_from_the_page_data(tmp_path):
    studio = Studio(tmp_path)
    result = studio.run(service.research_company(studio.client, "IT", page_id=PAGE_ID, as_of=AS_OF))
    assert result["ok"] and result["mode"] == "company" and result["source"] == "structured"
    assert result["library_total"] == 194 and result["ads_parsed"] == 5
    assert result["page"]["page_id"] == PAGE_ID and result["page"]["name"] == "Kingshot"
    assert result["signals"]["active_ads"] == 194 and result["signals"]["video_share"] == 1.0
    assert result["signals"]["reach"]["available"] is False
    assert all(ad["verdict"] in ("scaling", "holding", "testing", "review", "average") for ad in result["ads"])
    assert all(ad["reliability"] == "medium" and ad["scale_basis"] == "impressions" for ad in result["ads"])
    assert "view_all_page_id" in studio.renders[0]


def deep_result(studio, top_n=2, frames=False, events=None, ceiling=2):
    async def flow():
        result = await service.research_company(studio.client, "IT", page_id=PAGE_ID, as_of=AS_OF)
        return await service.deepen(studio.client, result, top_n, frames, events.append if events is not None else None,
                                    ceiling=ceiling)
    return studio.run(flow())


def test_reach_is_read_only_for_the_top_ads(tmp_path):
    studio, events = Studio(tmp_path), []
    result = deep_result(studio, top_n=2, events=events)
    top, rest = result["ads"][:2], result["ads"][2:]
    assert studio.opened == [ad["library_id"] for ad in top]
    assert all(ad["reach"]["eu_total"] == 7398228 and ad["reach"]["country_reach"] == 835585 for ad in top)
    assert all(ad["reach_per_day"] > 0 and ad["audience"]["age_min"] == 25 for ad in top)
    assert all("reach" not in ad for ad in rest)
    note = result["deep"].pop("ceiling_note")
    assert result["deep"] == {"requested": 2, "read": 2, "concepts": 2, "failed": [], "with_reach": 2,
                              "frames": False, "ceiling": 2, "capped": True, "left_out": 2, "note": None}
    # the ceiling of two ads left the second and third ad of the first concept closed, and the result says so
    assert note.startswith("Stopped at the ceiling of 2 ads opened: 2 of the 2 concepts asked for were read; 2 more")
    assert result["signals"]["reach"]["ads_with_reach"] == 2
    assert result["signals"]["audience"]["locations_included"][0]["ads"] == 2
    assert result["page"]["category"] == "Game Publisher" and result["page"]["logo_path"]
    assert [e["done"] for e in events] == [1, 2]
    assert service.estimate_deep(result, 2)["seconds"] > 0


def test_follow_up_page_loads_wait_only_a_short_gap(tmp_path):
    studio = Studio(tmp_path)
    deep_result(studio, top_n=1)
    assert studio.sleeps[0] == 5.0            # list, then detail views: 5 s apart, not 20


def test_second_run_reads_details_from_the_cache(tmp_path):
    studio = Studio(tmp_path)
    deep_result(studio, top_n=2)
    studio.opened.clear(), studio.sessions.clear()
    again = deep_result(studio, top_n=2)
    assert studio.opened == [] and studio.sessions == []
    assert again["ads"][0]["reach"]["available"]


def test_thumbnails_logos_and_frames_are_saved_locally(tmp_path):
    studio = Studio(tmp_path)
    result = deep_result(studio, top_n=2, frames=True)
    for ad in result["ads"][:2]:
        assert Path(ad["thumbnail_path"]).read_bytes().startswith(b"\xff\xd8")
        assert Path(ad["logo_path"]).name == f"page_{PAGE_ID}_logo.jpg"
        assert len(ad["frames"]) == 3 and all(Path(p).exists() for p in ad["frames"])
    assert len(studio.downloads) == 3          # two thumbnails, one logo shared by the page
    assert "thumbnail_path" not in result["ads"][2]


def test_ads_without_a_reach_section_are_reported_plainly(tmp_path):
    bare = fixture("ad_details_no_eu_reach.json")
    block = bare["data"]["ad_library_main"]["ad_details"]["transparency_by_location"]
    for key in block:
        block[key] = None
    studio = Studio(tmp_path)
    studio._detail = bare
    result = deep_result(studio, top_n=2)
    assert result["deep"]["with_reach"] == 0 and "European Union" in result["deep"]["note"]
    assert result["ads"][0]["reach"]["available"] is False
    assert "European Union" in result["signals"]["reach"]["note"]
    markdown = report.to_markdown(result, service.copy_report(result, 2), 2, AS_OF)
    assert "not published" in markdown


def test_report_shows_signals_reach_and_locations(tmp_path):
    studio = Studio(tmp_path)
    result = deep_result(studio, top_n=2)
    markdown = report.to_markdown(result, service.copy_report(result, 3), 3, AS_OF)
    assert "## Signals" in markdown and "Active ads: 194 in the library" in markdown
    assert "## Reach and audience of the top ads" in markdown and "7,398,228" in markdown
    assert "Locations targeted:" in markdown and "Italy (2)" in markdown
    rows = report.csv_rows(result["ads"])
    assert rows[0]["reach_eu"] == 7398228 and rows[0]["reach_country"] == 835585
    assert rows[0]["age_min"] == 25 and "Italy" in rows[0]["locations_included"]
    assert rows[0]["platforms"].startswith("facebook") and rows[2]["reach_eu"] is None


def test_failed_downloads_do_not_break_a_search(tmp_path):
    def broken(url):
        raise OSError("address expired")

    store = MediaStore(tmp_path / "media", fetcher=broken)
    ads = [{"library_id": "1", "page_id": "9", "image_url": "https://x.example/a.jpg",
            "logo_url": "https://x.example/l.jpg"}]
    assert save_ad_media(ads, store) == 0
    assert ads[0]["thumbnail_path"] is None and ads[0]["logo_path"] is None
    assert MediaStore(tmp_path / "m2", fetcher=lambda url: (b"<html>", "text/html")).save(
        "https://x.example/a.jpg", "a") is None
    assert store.save("http://x.example/a.jpg", "a") is None


def test_company_tools_over_mcp(tmp_path, monkeypatch):
    from fastmcp import Client

    studio = Studio(tmp_path)
    monkeypatch.setattr(server, "_client", studio.client)

    async def run():
        async with Client(server.mcp) as client:
            pages = (await client.call_tool("find_advertiser_pages", {"name": "Zalando", "country": "IT"})).data
            choose = (await client.call_tool("analyze_company", {"country": "IT", "name": "Zalando"})).data
            company = (await client.call_tool("analyze_company", {
                "country": "IT", "page_id": PAGE_ID, "deep_ads": 2, "max_results": 3})).data
            return pages, choose, company

    pages, choose, company = asyncio.run(run())
    assert pages["suggested_page_id"] == "365604620536"
    assert choose["outcome"] == "choose_page"
    # two concepts asked: their most shown ads, then the second and third ad of the first concept
    assert company["ok"] and len(company["ads"]) == 3 and company["deep"]["read"] == 4
    assert company["deep"]["concepts"] == 2 and company["deep"]["capped"] is False
    assert company["ads"][0]["reach"]["eu_total"] == 7398228


def test_reading_goes_on_until_the_concepts_asked_for_are_read_or_the_ceiling_is_hit(tmp_path):
    # default ceiling: two ads for every concept asked. Two concepts asked: both read, plus two more ads of the first
    studio = Studio(tmp_path)
    result = deep_result(studio, top_n=2, ceiling=None)
    assert result["deep"]["concepts"] == 2 and result["deep"]["read"] == 4 and result["deep"]["ceiling"] == 4
    assert result["deep"]["capped"] is False and result["deep"]["left_out"] == 0
    assert result["deep"]["ceiling_note"] is None
    assert len(studio.opened) == 4 and len(set(studio.opened)) == 4
    plan = service.estimate_deep(result, 2)
    assert (plan["ads"], plan["concepts"], plan["ceiling"]) == (4, 2, 4)
    # more concepts asked than the list holds: every concept is read, nothing is called a ceiling
    everything = deep_result(Studio(tmp_path / "all"), top_n=10, ceiling=None)
    assert everything["deep"]["concepts"] == 3 and everything["deep"]["read"] == 5 and not everything["deep"]["capped"]


def test_a_concept_that_cannot_be_opened_is_replaced_by_the_next_one(tmp_path):
    studio = Studio(tmp_path)
    reader = studio.client.read_details
    calls = []

    async def first_one_fails(url, library_ids, *args, **kwargs):
        calls.append(list(library_ids))
        outcomes = await reader(url, library_ids, *args, **kwargs)
        if len(calls) == 1:
            outcomes[library_ids[0]] = {"ok": False, "error": "closed", "attempts": 1, "from_cache": False}
        return outcomes

    studio.client.read_details = first_one_fails
    result = deep_result(studio, top_n=1, ceiling=2)
    # one concept asked, its ad did not open: the next concept of the list is read in its place, within the ceiling
    assert len(calls) == 2 and len(calls[0]) + len(calls[1]) == 2          # never past the ceiling of two ads
    assert calls[1][0] not in calls[0]
    assert result["deep"]["concepts"] == 1 and result["deep"]["failed"] == [calls[0][0]]
    assert result["deep"]["read"] == 1
