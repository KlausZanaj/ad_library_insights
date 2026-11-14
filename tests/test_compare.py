"""Two companies side by side: the comparison itself, the app job and the MCP tool."""
import asyncio
import copy
import json
import time

import pytest
from fastmcp import Client
from starlette.testclient import TestClient

from ad_library_insights import compare, server, service
from ad_library_insights.web.app import STATIC, create_app
from test_company import PAGE_ID, Studio

OTHER_PAGE = "365604620536"


@pytest.fixture
def company(tmp_path):
    studio = Studio(tmp_path)

    async def flow():
        result = await service.research_company(studio.client, "IT", page_id=PAGE_ID)
        return await service.deepen(studio.client, result, 2)

    return asyncio.run(flow())


def smaller(result):
    """A second company: a quarter of the ads, half of them video, slower, nothing scaling."""
    other = copy.deepcopy(result)
    other["page"]["name"] = "Northwind Desks"
    found = other["signals"]
    found.update(active_ads=found["active_ads"] // 4, video_share=0.5, new_per_week=2.0,
                 verdicts={"testing": 5})
    result["signals"]["verdicts"] = {"scaling": 2, "holding": 1}
    found["reach"]["median_reach_per_day"] = found["reach"]["median_reach_per_day"] // 10
    return other


def test_profile_holds_the_comparable_facts(company):
    facts = compare.profile(company)
    assert facts["active_ads"] == 194 and facts["video_share"] == 1.0
    assert facts["median_reach_per_day"] > 0 and facts["ads_with_reach"] == 2
    assert facts["age_range"] == "25-65" and facts["genders"] == ["All"]
    assert facts["locations_included"][0]["name"] and facts["locations_count"] == 27
    assert facts["buttons"][0] == {"label": "Install Now", "share": 1.0}
    assert facts["platforms"][0]["label"] == "facebook"


def test_rows_follow_one_order_in_four_groups(company):
    found = compare.compare(company, smaller(company))
    assert found["names"] == {"a": "Kingshot", "b": "Northwind Desks"} and found["country"] == "IT"
    assert [row["key"] for row in found["rows"]] == [key for _, key, _ in compare.ROWS]
    assert list(dict.fromkeys(row["group"] for row in found["rows"])) == ["pace", "creative", "reach", "route"]
    active = next(row for row in found["rows"] if row["key"] == "active_ads")
    assert (active["a"], active["b"], active["kind"]) == (194, 48, "number")
    assert "no spend and no sales" in found["note"]


def test_differences_worth_noting_name_the_leading_side(company):
    notes = {note["key"]: note for note in compare.compare(company, smaller(company))["highlights"]}
    assert set(notes) == {"active_ads", "median_reach_per_day", "video_share", "scaling_ads", "holding_ads"}
    assert notes["scaling_ads"] == {"key": "scaling_ads", "leader": "a", "lead": 2, "trail": 0}
    assert notes["active_ads"] == {"key": "active_ads", "leader": "a", "ratio": 4.0, "lead": 194, "trail": 48}
    assert notes["median_reach_per_day"]["leader"] == "a" and notes["median_reach_per_day"]["ratio"] >= 9.9
    assert notes["video_share"]["lead"] == 1.0 and notes["video_share"]["trail"] == 0.5
    swapped = {note["key"]: note for note in compare.compare(smaller(company), company)["highlights"]}
    assert all(note["leader"] == "b" for note in swapped.values())


def test_close_companies_have_no_highlights(company):
    assert compare.compare(company, copy.deepcopy(company))["highlights"] == []


def test_missing_reach_is_left_empty_not_guessed(company):
    blind = copy.deepcopy(company)
    blind["signals"]["reach"] = {"available": False, "note": "n/a", "checked_ads": 2}
    found = compare.compare(company, blind)
    row = next(row for row in found["rows"] if row["key"] == "median_reach_per_day")
    assert row["a"] and row["b"] is None
    assert "median_reach_per_day" not in {note["key"] for note in found["highlights"]}


def test_every_row_group_and_highlight_has_a_label_in_both_languages():
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    for words in strings.values():
        for group, key, _ in compare.ROWS:
            assert f"cmp.row.{key}" in words and f"cmp.group.{group}" in words
        for key in ("active_ads", "new_per_week", "median_reach_per_day", "video_share", "scaling_ads", "holding_ads"):
            assert f"hl.{key}" in words


# --- app and MCP ----------------------------------------------------------------------

def run_job(client, **body):
    job = client.post("/api/jobs", json=body).json()
    for _ in range(200):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_app_compares_two_pages_in_one_job(tmp_path):
    studio = Studio(tmp_path)
    with TestClient(create_app(studio.client, home=tmp_path / "home")) as client:
        job = run_job(client, mode="compare", page_id=PAGE_ID, page_id_b=OTHER_PAGE, country="IT",
                      level="plan", deep=1)
        assert job["status"] == "done" and job["params"]["level"] == "data"      # a comparison is code only
        result = job["result"]
        assert result["mode"] == "compare" and len(result["sides"]) == 2
        assert all(side["ads"][0]["thumbnail"].startswith("/media/") for side in result["sides"])
        assert result["sides"][0]["ads"][0]["reach"]["eu_total"] == 7398228
        assert len(result["comparison"]["rows"]) == len(compare.ROWS)
        assert len(studio.renders) == 2 and "view_all_page_id=365604620536" in studio.renders[1]
        assert len(client.get("/api/history").json()["subjects"]) >= 1            # both searches are saved

        for body in ({"mode": "compare", "page_id": PAGE_ID, "country": "IT"},
                     {"mode": "compare", "page_id": PAGE_ID, "page_id_b": PAGE_ID, "country": "IT"},
                     {"mode": "compare", "page_id": PAGE_ID, "page_id_b": "northwind", "country": "IT"}):
            assert client.post("/api/jobs", json=body).status_code == 400


def test_compare_companies_tool(tmp_path, monkeypatch):
    studio = Studio(tmp_path)
    monkeypatch.setattr(server, "_client", studio.client)

    async def run():
        async with Client(server.mcp) as client:
            found = (await client.call_tool("compare_companies", {
                "country": "IT", "page_id_a": PAGE_ID, "page_id_b": OTHER_PAGE, "deep_ads": 1, "top_ads": 2})).data
            same = (await client.call_tool("compare_companies", {
                "country": "IT", "page_id_a": PAGE_ID, "page_id_b": PAGE_ID})).data
            return found, same

    found, same = asyncio.run(run())
    assert found["ok"] and found["names"]["a"] == "Kingshot"
    assert len(found["rows"]) == len(compare.ROWS) and len(found["top_ads"]["a"]) == 2
    assert same == {"ok": False, "error": "pass two different pages"}
