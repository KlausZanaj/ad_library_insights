"""Saved searches and what changed between two of them."""
import asyncio
import copy
import time

import pytest
from fastmcp import Client
from starlette.testclient import TestClient

from ad_library_insights import history, records, server
from ad_library_insights.browser import PageSnapshot
from ad_library_insights.web.app import create_app
from test_company import FIXTURES, PAGE_ID, Studio


def ad(library_id, body, **extra):
    return {"library_id": library_id, "ad_url": f"https://www.facebook.com/ads/library/?id={library_id}",
            "advertiser": "Northwind Desks", "body": body, "headline": "Sit-stand desk", "cta": "Shop now",
            "landing_domain": "northwind.example", "media_type": "image", "started": "2026-01-05",
            "days_running": 30, "repetitions": 1, "longevity_score": 20.0, "tier": "testing", **extra}


def result(taken_at, ads, mode="company"):
    base = {"country": "DE", "fetched_at": taken_at, "ads_parsed": len(ads),
            "signals": {"active_ads": len(ads)}, "ads": ads}
    if mode == "company":
        return {**base, "mode": "company", "page": {"page_id": "42", "name": "Northwind Desks"}}
    return {**base, "query": "Standing Desk"}


MONDAY = "2026-06-01T09:00:00+00:00"
FRIDAY = "2026-06-05T09:00:00+00:00"


def test_subject_key_is_stable_across_searches():
    company = history.subject(result(MONDAY, []))
    assert company == {"key": "company:DE:42", "mode": "company", "label": "Northwind Desks",
                       "country": "DE", "page_id": "42"}
    keyword = history.subject(result(MONDAY, [], mode="keyword"))
    assert keyword["key"] == "keyword:DE:standing desk" and keyword["label"] == "Standing Desk"


def test_new_stopped_and_changed_ads():
    before = history.snapshot_of(result(MONDAY, [
        ad("1", "Raise your desk in 3 seconds. Now 20% off."),
        ad("2", "Still working hunched over?"),
        ad("3", "Free returns for 30 days."),
    ]))
    after = history.snapshot_of(result(FRIDAY, [
        ad("1", "Raise your desk in 3 seconds. Now 30% off.", cta="Learn more"),   # copy, offer, button
        ad("3", "Free returns for 30 days."),                                      # untouched
        ad("4", "Still working hunched over?"),                                    # new ad, known text
        ad("5", "The desk that grows with your team."),                            # new ad, new text
    ]))
    found = history.compare(before, after)
    assert found["counts"] == {"new": 2, "new_texts": 1, "stopped": 1, "changed": 1}
    assert {(a["library_id"], a["new_text"]) for a in found["new"]} == {("4", False), ("5", True)}
    assert [a["library_id"] for a in found["stopped"]] == ["2"]
    changed = found["changed"][0]
    assert changed["library_id"] == "1" and changed["fields"] == ["text", "button", "offer"]
    assert changed["before"]["cta"] == "Shop now" and "20% off" in changed["before"]["opening"]
    assert found["days_between"] == 4.0 and found["sample"] is False
    assert "body" not in found["new"][0] and "ids" not in found["new"][0]


def test_merged_ads_are_matched_through_any_of_their_ids():
    before = history.snapshot_of(result(MONDAY, [ad("1", "Same text", variant_ids=["2", "3"])]))
    after = history.snapshot_of(result(FRIDAY, [ad("2", "Same text", variant_ids=["3"])]))
    found = history.compare(before, after)                  # the oldest copy stopped, the group lives on
    assert found["counts"] == {"new": 0, "new_texts": 0, "stopped": 0, "changed": 0}


def test_rotating_variations_of_dynamic_ads_are_not_changes():
    before = history.snapshot_of(result(MONDAY, [ad("1", "Catalogue", headline="Shoe A", multiple_versions=True)]))
    after = history.snapshot_of(result(FRIDAY, [ad("1", "Catalogue", headline="Shoe B", multiple_versions=True)]))
    assert history.compare(before, after)["counts"]["changed"] == 0


def test_new_ads_are_listed_latest_launch_first():
    before = history.snapshot_of(result(MONDAY, [ad("1", "A")]))
    after = history.snapshot_of(result(FRIDAY, [ad("1", "A"), ad("2", "B", started="2026-03-01"),
                                                ad("3", "C", started="2026-06-04")]))
    assert [a["library_id"] for a in history.compare(before, after)["new"]] == ["3", "2"]


def test_keyword_changes_are_marked_as_a_sample():
    before = history.snapshot_of(result(MONDAY, [ad("1", "A")], mode="keyword"))
    after = history.snapshot_of(result(FRIDAY, [ad("2", "B")], mode="keyword"))
    assert history.compare(before, after)["sample"] is True


def test_survival_compares_ads_of_the_same_age():
    young = [ad(f"y{n}", f"Young {n}", days_running=3) for n in range(4)]
    old = [ad(f"o{n}", f"Old {n}", days_running=120) for n in range(5)]
    before = history.snapshot_of(result(MONDAY, young + old))
    after = history.snapshot_of(result(FRIDAY, young[:1] + old))           # three young ads were stopped
    found = history.compare(before, after)["survival"]
    assert found["measurable"] is True
    groups = {group["age"]: group for group in found["groups"]}
    assert groups["under 7 days"] == {"age": "under 7 days", "listed_before": 4, "still_listed": 1, "stopped": 3}
    assert groups["90 days or more"]["still_listed"] == 5 and groups["90 days or more"]["stopped"] == 0
    assert groups["7 to 29 days"]["listed_before"] == 0


def test_survival_is_not_measured_on_a_sample_or_a_partial_list():
    ads = [ad("1", "A"), ad("2", "B")]
    keyword = history.compare(history.snapshot_of(result(MONDAY, ads, mode="keyword")),
                              history.snapshot_of(result(FRIDAY, ads[:1], mode="keyword")))
    assert keyword["survival"] == {"measurable": False, "reason": "sample"}
    partial = result(MONDAY, ads)
    partial["signals"]["active_ads"] = 40                                  # two ads read out of forty
    found = history.compare(history.snapshot_of(partial), history.snapshot_of(result(FRIDAY, ads)))
    assert found["survival"] == {"measurable": False, "reason": "partial_list"}
    assert history.summary({"available": False, "reason": "first_search"})["available"] is False


def test_changes_need_a_second_search(tmp_path):
    store = history.History(tmp_path)
    assert store.changes("company:DE:42") == {"available": False, "reason": "never_searched",
                                              "subject": None, "snapshots": 0}
    first = store.record(result(MONDAY, [ad("1", "A")]))
    assert first["available"] is False and first["reason"] == "first_search" and first["snapshots"] == 1
    assert store.record(result(MONDAY, [ad("1", "A")]))["snapshots"] == 1        # same search, from the cache
    second = store.record(result(FRIDAY, [ad("1", "A"), ad("2", "B")]))
    assert second["available"] and second["counts"]["new"] == 1 and second["snapshots"] == 2
    assert history.summary(second) == {"available": True, "key": "company:DE:42",
                                       "previous_taken_at": MONDAY, "days_between": 4.0,
                                       "counts": second["counts"], "survival": second["survival"]}
    assert history.summary(first) == {"available": False, "reason": "first_search", "key": "company:DE:42"}


def test_searches_without_ads_are_not_saved(tmp_path):
    store = history.History(tmp_path)
    assert store.record(result(MONDAY, []))["reason"] == "no_ads"
    assert store.subjects() == []


def test_saved_searches_are_listed_latest_first_and_trimmed(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "KEEP", 3)
    store = history.History(tmp_path)
    for hour in range(5):
        store.record(result(f"2026-06-01T1{hour}:00:00+00:00", [ad("1", "A")]))
    store.record(result(FRIDAY, [ad("9", "Z")], mode="keyword"))
    listed = store.subjects()
    assert [row["mode"] for row in listed] == ["keyword", "company"]
    assert listed[1]["snapshots"] == 3 and listed[1]["last_taken_at"].startswith("2026-06-01T14")
    assert len(store.snapshots("company:DE:42")) == 3


# --- through the app and the MCP tools --------------------------------------------------

def later_page(studio):
    """Make the next page load differ: one ad gone, one with new copy, at a later time."""
    connection = records.connection_from_text((FIXTURES / "search_results_page.json").read_text("utf-8"))
    edges = copy.deepcopy(connection["edges"])
    removed = edges.pop(3)["node"]["collated_results"][0]["ad_archive_id"]   # the only ad with its text
    edited = edges[0]["node"]["collated_results"][0]
    edited["snapshot"]["body"]["text"] = "A new line of copy, now 50% off"

    async def render(url, wait_seconds, scroll_rounds):
        studio.now += 86_400
        return PageSnapshot(url=url, status_code=403, page_text="~190 results", edges=edges,
                            total_count=connection["count"])

    studio.client._renderer = render
    return removed, edited["ad_archive_id"]


def run_job(client, **body):
    job = client.post("/api/jobs", json=body).json()
    for _ in range(200):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_app_reports_changes_from_the_second_search(tmp_path):
    studio = Studio(tmp_path)
    body = {"mode": "company", "page_id": PAGE_ID, "country": "IT", "level": "data", "deep": 1}
    with TestClient(create_app(studio.client, home=tmp_path / "home")) as client:
        first = run_job(client, **body)["result"]
        assert first["changes"] == {"available": False, "reason": "first_search", "key": f"company:IT:{PAGE_ID}"}
        assert client.get("/api/history").json()["subjects"][0]["snapshots"] == 1

        removed, edited = later_page(studio)
        second = run_job(client, **body, fresh=True)["result"]
        counts = second["changes"]["counts"]
        assert second["changes"]["available"] and counts["stopped"] >= 1 and counts["changed"] + counts["new"] >= 1

        listed = client.get("/api/history").json()["subjects"]
        assert listed[0]["label"] == "Kingshot" and listed[0]["snapshots"] == 2
        found = client.get("/api/history/changes", params={"key": second["changes"]["key"]}).json()
        assert found["available"] and found["days_between"] == 1.0
        gone = {a["library_id"] for a in found["stopped"]}
        assert removed in gone or any(removed in a.get("library_id", "") for a in found["stopped"])
        touched = [a for a in found["changed"] + found["new"] if a["library_id"] == edited]
        assert touched and all("thumbnail" in a and "thumbnail_path" not in a for a in found["stopped"])
        assert client.get("/api/history/changes", params={"key": "keyword:IT:none"}).json()["available"] is False


def test_what_changed_tool(tmp_path, monkeypatch):
    studio = Studio(tmp_path)
    monkeypatch.setattr(server, "_client", studio.client)

    async def run():
        async with Client(server.mcp) as client:
            await client.call_tool("analyze_company", {"country": "IT", "page_id": PAGE_ID, "deep_ads": 0})
            first = (await client.call_tool("what_changed", {"country": "it", "page_id": PAGE_ID})).data
            later_page(studio)
            again = (await client.call_tool("analyze_company", {
                "country": "IT", "page_id": PAGE_ID, "deep_ads": 0, "use_cache": False})).data
            second = (await client.call_tool("what_changed", {"country": "IT", "page_id": PAGE_ID})).data
            listed = (await client.call_tool("what_changed", {})).data
            return first, again, second, listed

    first, again, second, listed = asyncio.run(run())
    assert first["available"] is False and first["reason"] == "first_search"
    assert again["changes"]["available"]
    assert second["available"] and second["counts"]["stopped"] >= 1
    assert listed["searches"][0]["key"] == f"company:IT:{PAGE_ID}"


def test_snapshot_keeps_additive_reach_status_and_audience_distribution():
    rich = ad(
        "9",
        "Desk copy",
        status="inactive",
        ended="2026-06-10",
        impression_rank=2,
        reach_total=500,
        reach_per_day=50,
        reach_cards_read=1,
        reach={
            "eu_total": 1200,
            "uk_total": 300,
            "breakdown_3d": [
                {"country": "IT", "age_range": "25-34", "male": 300, "female": 150, "unknown": 50, "reach": 500},
                {"country": "DE", "age_range": "35-44", "male": 500, "female": 0, "unknown": 0, "reach": 500},
            ],
        },
    )
    snap = history.snapshot_of(result(MONDAY, [rich]))
    stored = snap["ads"][0]
    assert stored["status"] == "inactive" and stored["ended"] == "2026-06-10"
    assert stored["impression_rank"] == 2 and stored["reach_total"] == 500
    assert stored["reach_per_day"] == 50 and stored["reach_cards_read"] == 1
    assert stored["eu_total"] == 1200 and stored["uk_total"] == 300
    dist = snap["audience_distribution"]
    assert dist["ads_with_breakdown"] == 1 and dist["total_cell_reach"] == 1000
    assert pytest.approx(sum(c["share"] for c in dist["cells"]), abs=1e-5) == 1.0
    assert history.snapshot_of(result(MONDAY, [ad("1", "Plain")]))["audience_distribution"] is None
