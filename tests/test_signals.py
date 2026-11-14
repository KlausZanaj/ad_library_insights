"""Signals computed by code: language, audience breadth, reach per day, search summaries."""
from datetime import date

import pytest

from ad_library_insights import rating, signals

AS_OF = date(2026, 6, 30)


def ad(library_id, started, body, advertiser="Northwind Desks", copies=1, **extra):
    return {"library_id": library_id, "started": started, "ended": None, "status": "active",
            "advertiser": advertiser, "body": body, "copies": copies, "media_type": "image",
            "cta": "Shop now", "landing_domain": "northwind.example", "platforms": ["facebook"],
            **extra}


def reach(total, country=None, countries=1):
    return {"available": True, "basis": "EU", "basis_total": total, "eu_total": total,
            "uk_total": None, "country": "DE", "country_reach": total if country is None else country,
            "countries_reached": countries, "regions": [{"region": "EU", "total": total,
                                                         "countries": [{"country": "DE", "reach": country or total}]}]}


AUDIENCE = {"age_min": 18, "age_max": 65, "gender": "All",
            "locations_included": [{"name": "Germany", "type": "countries", "excluded": False}],
            "locations_excluded": []}


@pytest.mark.parametrize("text, expected", [
    ("The best desk for your home and your back", "en"),
    ("Scopri la scrivania più comoda per la tua schiena, con il nostro sconto", "it"),
    ("Die beste Lösung für dein Büro und deine Gesundheit", "de"),
    ("Ich kann nicht glauben, dass ich acht Stunden gespielt habe", "de"),
    ("Heroes Needed for Survival!", "en"),          # a short text: one common word is enough
    ("생존을 위한 영웅이 필요하다", "ko"),
    ("OK!", None),
])
def test_language_guess(text, expected):
    assert signals.detect_language(text) == expected


def test_reach_per_day_and_breadth_are_added_when_reach_is_known():
    ranked = rating.group_concepts([ad("1", "2026-06-20", "Ten days of reach"),
                                    ad("2", "2026-06-25", "No detail view read")], AS_OF)
    first = next(a for a in ranked if a["library_id"] == "1")
    first.update(reach=reach(50_000, country=20_000), audience=AUDIENCE)
    signals.annotate(ranked)
    # the country that was searched is what counts: 20,000 people there, out of 50,000 in the EU
    assert first["reach_total"] == 20_000 and first["reach_per_day"] == 2_000 and first["reach_in_market"]
    assert first["reach"]["eu_total"] == 50_000 and "reach_elsewhere_per_day" not in first
    assert first["audience_breadth"]["label"] == "broad"
    other = next(a for a in ranked if a["library_id"] == "2")
    assert "reach_per_day" not in other and other["verdict"] == "testing"


def test_reach_per_day_uses_the_days_of_the_ad_that_was_opened():
    # the concept started in January; the most shown ad of the group started ten days ago
    ranked = rating.group_concepts([ad("old", "2026-01-01", "Same text", impression_rank=9),
                                    ad("new", "2026-06-20", "Same text", impression_rank=1)], AS_OF)
    concept = ranked[0]
    assert concept["library_id"] == "new" and concept["days_running"] == 180 and concept["ad_days"] == 10
    concept["reach"] = reach(50_000)
    signals.annotate(ranked)
    assert concept["reach_per_day"] == 5_000


def test_reach_per_day_is_never_divided_by_fewer_than_seven_days():
    ranked = rating.group_concepts([ad("1", "2026-06-29", "One day on air")], AS_OF)
    ranked[0]["reach"] = reach(70_000)
    signals.annotate(ranked)
    assert ranked[0]["days_running"] == 1 and ranked[0]["reach_per_day"] == 10_000
    assert ranked[0]["too_recent"] and ranked[0]["verdict"] == "testing"


def test_reach_outside_the_searched_country_is_kept_apart():
    ranked = rating.group_concepts([ad("1", "2026-06-10", "Twenty days on air")], AS_OF)
    ranked[0]["reach"] = {**reach(60_000), "country": "US", "country_reach": None}
    signals.annotate(ranked)
    assert ranked[0]["reach_in_market"] is False and ranked[0]["reach_elsewhere_per_day"] == 3_000
    assert "reach_per_day" not in ranked[0] and "reach_total" not in ranked[0]


def test_narrow_audience_is_labelled():
    narrow = {"age_min": 25, "age_max": 34, "gender": "Women", "locations_excluded": [],
              "locations_included": [{"name": "Munich", "type": "cities", "excluded": False}]}
    assert signals.audience_breadth(narrow, None)["label"] == "narrow"
    assert signals.audience_breadth(None, None) is None


def company(reaches=None):
    """Five ads of one advertiser; "old" has run longest."""
    ads = [ad("old", "2026-01-01", "An old single ad"),
           ad("a", "2026-04-01", "Repeated text", copies=4),
           ad("b", "2026-05-20", "Fresh idea one"),
           ad("c", "2026-06-01", "Fresh idea two"),
           ad("d", "2026-06-10", "Fresh idea three")]
    ranked = rating.group_concepts(ads, AS_OF)
    for item in ranked:
        if reaches and item["library_id"] in reaches:
            item["reach"] = reach(reaches[item["library_id"]])
    return signals.annotate(ranked)


def test_summary_of_a_search():
    cards = [
        ad("1", "2026-06-25", "Still working hunched over? Get the desk your back needs.",
           media_type="video", platforms=["facebook", "instagram"]),
        ad("2", "2026-06-10", "Still working hunched over? Get the desk your back needs.",
           media_type="video"),
        ad("3", "2026-05-01", "Stanco della solita scrivania? Scopri quella più adatta alla tua schiena.",
           cta="Learn more", landing_domain="aurora.example"),
        ad("4", "2026-01-15", "The desk that grows with you and your team.", copies=3),
    ]
    ranked = signals.annotate(rating.group_concepts(cards, AS_OF))
    found = signals.summarize(cards, ranked, AS_OF, library_total=40, country="DE")
    assert found["active_ads"] == 40 and found["ads_loaded"] == 4 and found["distinct_texts"] == 3
    assert found["video_share"] == 0.5 and found["format_share"] == {"video": 0.5, "image": 0.5}
    assert found["started_last_30_days"] == 2 and found["new_per_week"] == 0.5
    assert len(found["weekly_launches"]) == 8 and found["weekly_launches"][-1]["ads"] == 0
    assert found["languages"][0] == {"language": "en", "ads": 3, "share": 0.75}
    assert found["buttons"][0] == {"button": "Shop Now", "ads": 3, "share": 0.75}
    assert found["destinations"][0]["domain"] == "northwind.example"
    assert found["platforms"][0] == {"platform": "facebook", "ads": 4, "share": 1.0}
    patterns = found["copy_patterns"]
    assert patterns["reused_texts"][0]["creatives"] == 2 and patterns["reused_texts"][0]["ads"] == 2
    assert patterns["repeated_openers"] == []          # merged texts count once
    assert sum(found["verdicts"].values()) == 3 and found["reliability"] == {"low": 3}
    assert found["reach"]["available"] is False and "detail view" in found["reach"]["note"]
    assert found["audience"] is None
    assert signals.summarize(cards, ranked, AS_OF)["active_ads"] == 6   # sums the counters


def test_summary_reports_reach_and_locations_after_details_were_read():
    ranked = company({"old": 1_800, "a": 900_000, "b": 400_000})
    for item in ranked:
        if "reach" in item:
            item["audience"] = {**AUDIENCE, "locations_included": AUDIENCE["locations_included"] + [
                {"name": "South America", "type": "country_groups", "excluded": False}],
                "locations_excluded": [{"name": "Bavaria", "type": "regions", "excluded": True}]}
    next(a for a in ranked if a["library_id"] == "c")["reach"] = {"available": False, "note": "n/a"}
    signals.annotate(ranked)
    found = signals.refresh(signals.summarize(ranked, ranked, AS_OF), ranked, "DE")
    assert found["reach"]["ads_with_reach"] == 3 and found["reach"]["ads_without_reach"] == 1
    assert found["reach"]["eu_reach_summed"] == 1_301_800
    assert found["reach"]["top_countries"][0]["country"] == "DE"
    assert found["needs_review"] == 1 and found["verdicts"]["review"] == 1      # the old ad, ten people a day
    assert found["reliability"]["high"] == 3
    places = {p["name"]: p for p in found["audience"]["locations_included"]}
    assert places["South America"] == {"name": "South America", "type": "country_groups", "ads": 3}
    assert found["audience"]["locations_excluded"][0]["name"] == "Bavaria"
    assert found["audience"]["breadth"] == {"broad": 3}


def test_summary_says_when_no_checked_ad_has_reach():
    ranked = company()
    for item in ranked[:2]:
        item["reach"] = {"available": False, "note": "n/a"}
    found = signals.refresh(signals.summarize(ranked, ranked, AS_OF), ranked)
    assert found["reach"]["available"] is False and found["reach"]["checked_ads"] == 2
    assert "European Union" in found["reach"]["note"]
