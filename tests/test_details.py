"""Reach and audience from saved detail responses, and the pacing of many detail reads."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from ad_library_insights import details
from ad_library_insights.storage import DiskCache

FIXTURES = Path(__file__).parent / "fixtures"


def payload(name):
    return json.loads((FIXTURES / f"ad_details_{name}.json").read_text(encoding="utf-8"))


def test_reach_over_many_eu_countries():
    found = details.parse_details(payload("eu_many_countries"), "IT")
    reach = found["reach"]
    assert reach["available"] and reach["basis"] == "EU"
    assert reach["eu_total"] == 7398228 and reach["uk_total"] == 1679270
    assert reach["country"] == "IT" and reach["country_reach"] == 835585   # from the breakdown
    eu = next(r for r in reach["regions"] if r["region"] == "EU")
    assert len(eu["countries"]) == 26
    assert eu["countries"][0]["reach"] >= eu["countries"][-1]["reach"]
    assert {row["age_range"] for row in reach["by_age"]} >= {"25-34", "65+"}
    assert reach["by_gender"]["male"] > reach["by_gender"]["female"]


def test_audience_and_chosen_locations():
    audience = details.parse_details(payload("eu_many_countries"), "IT")["audience"]
    assert (audience["age_min"], audience["age_max"], audience["gender"]) == (25, 65, "All")
    names = {place["name"] for place in audience["locations_included"]}
    assert {"Italy", "France", "United Kingdom"} <= names
    assert audience["locations_excluded"] == []


def test_single_country_reach_matches_the_section_total():
    reach = details.parse_details(payload("eu_one_country"), "IT")["reach"]
    assert reach["eu_total"] == 2692918 and reach["country_reach"] == 2692918
    assert reach["uk_total"] is None and reach["countries_reached"] == 1


def test_a_covered_country_missing_from_the_breakdown_was_not_reached():
    # the ad was delivered in Italy only: Germany is an EU country the section would list
    assert details.parse_details(payload("eu_one_country"), "DE")["reach"]["country_reach"] == 0
    # the United States are in no section: nothing can be said, which is not the same as zero
    assert details.parse_details(payload("eu_one_country"), "US")["reach"]["country_reach"] is None


def test_sections_are_read_by_presence_not_by_a_country_list():
    # delivered in the United Kingdom only: no EU section, yet reach is there
    reach = details.parse_details(payload("no_eu_reach"), "US")["reach"]
    assert reach["available"] and reach["basis"] == "UK"
    assert reach["eu_total"] is None and reach["uk_total"] == 279161
    assert reach["country_reach"] is None


def test_an_ad_without_any_section_says_so():
    bare = copy.deepcopy(payload("no_eu_reach"))
    block = bare["data"]["ad_library_main"]["ad_details"]["transparency_by_location"]
    for key in block:
        block[key] = None
    found = details.parse_details(bare, "BR")
    assert found["reach"]["available"] is False
    assert "European Union" in found["reach"]["note"]
    assert found["audience"] is None
    assert found["page"]["name"]


def test_areas_and_exclusions_are_kept_as_the_advertiser_chose_them():
    custom = copy.deepcopy(payload("eu_one_country"))
    eu = custom["data"]["ad_library_main"]["ad_details"]["transparency_by_location"]["eu_transparency"]
    eu["location_audience"] += [{"name": "South America", "type": "country_groups", "excluded": False},
                                {"name": "Sicily", "type": "regions", "excluded": True}]
    audience = details.parse_details(custom, "IT")["audience"]
    assert {"name": "South America", "type": "country_groups", "excluded": False} in audience["locations_included"]
    assert [place["name"] for place in audience["locations_excluded"]] == ["Sicily"]


def test_page_facts_and_payer():
    found = details.parse_details(payload("eu_many_countries"))
    assert found["page"]["name"] == "Kingshot" and found["page"]["followers"] == 2596792
    assert found["page"]["logo_url"].startswith("https://")
    assert found["payer"] == "Kingshot"
    with pytest.raises(ValueError):
        details.parse_details({"data": {}})


# --- pacing ---------------------------------------------------------------------------

class FakeSession:
    """Answers from a script: a number is how long the answer takes, an exception a failure."""

    def __init__(self, bench, script):
        self.bench, self.script, self.opened = bench, dict(script), []

    async def open(self, library_id):
        self.opened.append(library_id)
        steps = self.script.get(library_id, [0.4])
        step = steps.pop(0) if len(steps) > 1 else steps[0]
        if isinstance(step, Exception):
            self.bench.now += 15
            raise step
        self.bench.now += step
        return payload("eu_one_country")


class Bench:
    def __init__(self, tmp_path, script=None, **options):
        self.now, self.sleeps, self.events = 0.0, [], []
        self.cache = DiskCache(tmp_path / "cache", clock=lambda: 1_000.0)
        self.session = FakeSession(self, script or {})
        self.collector = details.DetailCollector(
            cache=self.cache, sleep=self._sleep, clock=lambda: self.now, jitter=lambda: 0.0, **options)

    async def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def collect(self, ids, **kwargs):
        return asyncio.run(self.collector.collect(self.session, ids, "IT", self.events.append, **kwargs))


def test_steady_pace_between_ads(tmp_path):
    bench = Bench(tmp_path)
    results = bench.collect(["1", "2", "3"])
    assert all(r["ok"] and r["attempts"] == 1 for r in results.values())
    assert bench.sleeps == [1.0, 1.0]                      # no pause before the first
    assert results["1"]["details"]["reach"]["eu_total"] == 2692918


def test_progress_counts_up_and_estimates_time_left(tmp_path):
    bench = Bench(tmp_path)
    bench.collect(["1", "2", "3", "4"])
    assert [e["done"] for e in bench.events] == [1, 2, 3, 4]
    assert all(e["total"] == 4 for e in bench.events)
    assert bench.events[0]["eta_seconds"] > bench.events[2]["eta_seconds"] > 0
    assert bench.events[-1]["eta_seconds"] == 0


def test_slow_answers_stretch_the_pause_and_quick_ones_ease_it(tmp_path):
    bench = Bench(tmp_path, {"2": [9.0]})
    bench.collect([str(n) for n in range(1, 10)])
    assert bench.sleeps[0] == 1.0          # before the slow one
    assert bench.sleeps[1] == 2.0          # right after it
    assert bench.sleeps[-1] == 1.0         # back to normal after five quick answers


def test_failed_ad_is_retried_with_growing_waits(tmp_path):
    bench = Bench(tmp_path, {"1": [TimeoutError("late"), TimeoutError("late"), 0.4]})
    results = bench.collect(["1"])
    assert results["1"]["ok"] and results["1"]["attempts"] == 3
    assert bench.sleeps == [5.0, 15.0]


def test_stops_asking_when_the_page_keeps_refusing(tmp_path):
    script = {str(n): [TimeoutError("refused")] for n in range(1, 6)}
    bench = Bench(tmp_path, script, max_retries=1)
    results = bench.collect(["1", "2", "3", "4", "5"])
    assert [results[str(n)]["ok"] for n in range(1, 6)] == [False] * 5
    assert bench.session.opened.count("4") == 0 and bench.session.opened.count("5") == 0
    assert results["5"]["error"].startswith("skipped")
    assert "TimeoutError" in results["1"]["error"]
    assert [e["status"] for e in bench.events] == ["failed"] * 3 + ["skipped"] * 2


def test_cached_details_are_not_fetched_again(tmp_path):
    bench = Bench(tmp_path)
    bench.collect(["1", "2"])
    bench.session.opened.clear()
    again = bench.collect(["1", "2", "3"])
    assert bench.session.opened == ["3"]
    assert again["1"]["from_cache"] and not again["3"]["from_cache"]
    assert bench.collect(["1"], use_cache=False)["1"]["from_cache"] is False


def test_time_estimate_grows_with_ads_and_frames():
    assert details.estimate_seconds(0) == 0
    assert details.estimate_seconds(10) < details.estimate_seconds(20) < details.estimate_seconds(50)
    assert details.estimate_seconds(10, videos_with_frames=10) > details.estimate_seconds(10)
