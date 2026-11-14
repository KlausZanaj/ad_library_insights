"""The rating: one ad per concept, then scale, staying power and creative investment.

The first half uses small invented sets to pin each rule. The second half runs the
rating on three searches saved from the live Ad Library (cards and reach as read on
the day), which are the acceptance cases the rating was rebuilt for.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from ad_library_insights import rating, scoring, service, signals
from ad_library_insights.client import FetchResult

AS_OF = date(2026, 6, 30)
FIXTURES = Path(__file__).parent / "fixtures"


def ad(library_id, started="2026-06-01", body="Raise your desk in 3 seconds", advertiser="Northwind", **extra):
    return {"library_id": library_id, "started": started, "ended": None, "status": "active",
            "advertiser": advertiser, "body": body, "copies": 1, "media_type": "video", "format": "video",
            **extra}


def with_reach(ranked, totals):
    """Attach reach to concepts by library id and rate again."""
    for item in ranked:
        if item["library_id"] in totals:
            total = totals[item["library_id"]]
            item["reach"] = {"available": True, "basis": "EU", "basis_total": total, "eu_total": total,
                             "uk_total": None, "country_reach": total, "countries_reached": 1, "regions": []}
    return signals.annotate(ranked)


def by_id(ranked):
    return {item["library_id"]: item for item in ranked}


# --- one ad per concept ---------------------------------------------------------------

def test_identical_copies_are_not_creative_investment():
    ranked = rating.group_concepts([ad("1", copies=10, video_url="https://v/a.mp4")], AS_OF)
    assert ranked[0]["creatives"] == 1 and ranked[0]["copies_total"] == 10 and ranked[0]["cards"] == 1
    assert ranked[0]["score_parts"]["creative"] == 0.0


def test_the_same_video_under_one_text_counts_once():
    cards = [ad(str(n), copies=10, video_url="https://v/same.mp4", headline=f"Headline {n % 2}") for n in range(8)]
    concept = rating.group_concepts(cards, AS_OF)[0]
    assert (concept["creatives"], concept["cards"], concept["copies_total"], concept["kind"]) == (1, 8, 80, "standard")


def test_different_creatives_for_one_text_are_counted():
    cards = [ad(str(n), video_url=f"https://v/{n}.mp4") for n in range(5)]
    concept = rating.group_concepts(cards, AS_OF)[0]
    assert concept["creatives"] == 5 and concept["variant_ids"] and concept["score_parts"]["creative"] == 100.0


def test_catalogue_ads_are_one_creative_with_products():
    feed = [ad(str(n), format="dpa", multiple_versions=True, headline=f"Product {n}", video_url=None,
               image_url=f"https://i/{n}.jpg") for n in range(6)]
    concept = rating.group_concepts(feed, AS_OF)[0]
    assert (concept["kind"], concept["creatives"], concept["products"], concept["cards"]) == ("catalog", 1, 6, 6)
    by_links = [ad(str(n), landing_url=f"https://shop.example/p/{n}", video_url=f"https://v/{n}.mp4") for n in range(6)]
    assert rating.group_concepts(by_links, AS_OF)[0]["kind"] == "catalog"      # same text, a product behind each ad


def test_dynamic_ads_are_marked_as_versions():
    concept = rating.group_concepts([ad("1", format="dco", multiple_versions=True)], AS_OF)[0]
    assert concept["kind"] == "dynamic"


def test_translations_on_the_same_video_are_one_concept():
    cards = [ad("en", body="The desk that grows with your team", video_url="https://v/a.mp4"),
             ad("de", body="Der Tisch, der mit deinem Team wächst und für alle passt", video_url="https://v/a.mp4"),
             ad("other", body="A completely different idea for your office", video_url="https://v/b.mp4")]
    ranked = rating.group_concepts(cards, AS_OF)
    assert len(ranked) == 2
    merged = next(item for item in ranked if item["texts"] == 2)
    assert merged["languages"] == ["de", "en"] and merged["creatives"] == 1 and merged["cards"] == 2


def test_translations_are_recognised_by_emoji_and_digits_when_videos_differ():
    cards = [ad("en", body="I played this for 8 hours straight", video_url="https://v/en.mp4"),
             ad("de", body="Ich habe das 8 Stunden lang gespielt", video_url="https://v/de.mp4"),
             ad("es", body="¡No puedo creer que jugué 8 horas seguidas!", video_url="https://v/es.mp4")]
    ranked = rating.group_concepts(cards, AS_OF)
    assert len(ranked) == 1 and ranked[0]["texts"] == 3 and ranked[0]["creatives"] == 3


def test_same_language_texts_stay_apart_even_on_one_video():
    cards = [ad("1", body="Raise your desk in 3 seconds", video_url="https://v/a.mp4"),
             ad("2", body="Your back will thank you in 3 days", video_url="https://v/a.mp4")]
    assert len(rating.group_concepts(cards, AS_OF)) == 2


def test_the_concept_is_shown_through_its_most_seen_ad():
    cards = [ad("old", started="2026-01-01", impression_rank=40), ad("top", started="2026-06-20", impression_rank=3)]
    concept = rating.group_concepts(cards, AS_OF)[0]
    assert concept["library_id"] == "top" and concept["impression_rank"] == 3
    assert concept["started"] == "2026-01-01" and concept["days_running"] == 180 and concept["ad_days"] == 10


def test_the_earlier_longevity_score_is_kept_as_a_component():
    concept = rating.group_concepts([ad("1", started="2026-04-23", copies=6)], AS_OF)[0]
    assert concept["longevity_score"] == scoring.longevity_score(68, 6) == 76.5
    assert concept["longevity_parts"] == {"days": 45.3, "reuse": 31.1}
    assert concept["score"] != concept["longevity_score"]


# --- rating ---------------------------------------------------------------------------

def market():
    """Six advertisers, one ad each, listed by impressions in this order."""
    spec = [("giant", "2026-05-17", 1), ("steady", "2025-11-01", 2), ("shop", "2026-02-10", 3),
            ("forgotten", "2025-01-01", 4), ("fresh", "2026-06-22", 5), ("small", "2026-05-01", 6)]
    return [ad(name, started=started, body=f"Text of {name}", advertiser=name, impression_rank=rank)
            for name, started, rank in spec]


REACH = {"giant": 5_000_000, "steady": 480_000, "shop": 98_000, "forgotten": 49_000, "fresh": 2_400, "small": 12_000}


def test_without_reach_scale_comes_from_the_impression_position():
    ranked = by_id(rating.group_concepts(market(), AS_OF))
    assert all(item["reliability"] == "medium" and item["scale_basis"] == "impressions" for item in ranked.values())
    assert ranked["giant"]["score_parts"]["scale"] == 100.0 and ranked["small"]["score_parts"]["scale"] == 0.0
    assert ranked["giant"]["score_weights"] == {"scale": 50, "staying": 30, "creative": 20}
    assert ranked["small"]["verdict"] == "average" and ranked["fresh"]["verdict"] == "testing"


def test_with_reach_scale_is_people_per_day_on_a_log_scale_of_the_search():
    ranked = by_id(with_reach(rating.group_concepts(market(), AS_OF), REACH))
    assert all(item["reliability"] == "high" and item["scale_basis"] == "reach" for item in ranked.values())
    assert ranked["giant"]["reach_per_day"] == 113_636 and ranked["giant"]["score_parts"]["scale"] == 100.0
    assert ranked["forgotten"]["reach_per_day"] == 90 and ranked["forgotten"]["score_parts"]["scale"] == 0.0
    assert 20 < ranked["shop"]["score_parts"]["scale"] < 45          # 700 a day, between 90 and 113,636
    assert ranked["giant"]["score_weights"] == {"scale": 60, "staying": 25, "creative": 15}
    points = ranked["giant"]["score_points"]
    assert points == {"scale": 60.0, "staying": 12.2, "creative": 0.0} and ranked["giant"]["score"] == 72.2


def test_scale_decides_the_top_and_days_alone_cannot():
    ranked = with_reach(rating.group_concepts(market(), AS_OF), REACH)
    assert ranked[0]["library_id"] == "giant"                          # 44 days, most people per day
    forgotten = by_id(ranked)["forgotten"]
    assert forgotten["days_running"] == 545 and forgotten["score"] == 25.0      # full staying power, nothing else
    assert [item["library_id"] for item in ranked].index("forgotten") >= 3


def test_verdicts_in_plain_words():
    ranked = by_id(with_reach(rating.group_concepts(market(), AS_OF), REACH))
    assert ranked["giant"]["verdict"] == "scaling"
    assert ranked["steady"]["verdict"] == "holding"                    # 241 days, about 2,000 people a day
    assert ranked["forgotten"]["verdict"] == "review" and ranked["forgotten"]["needs_review"]
    assert ranked["forgotten"]["review"] == {"reason": "long_running_low_scale", "basis": "reach"}
    assert ranked["fresh"]["verdict"] == "testing"
    assert ranked["small"]["verdict"] == "average" and "review" not in ranked["small"]


def test_review_does_not_depend_on_copy_reuse():
    cards = market() + [ad("forgotten-2", started="2025-01-01", body="Text of forgotten", advertiser="forgotten",
                           impression_rank=7, video_url="https://v/other.mp4")]
    ranked = by_id(with_reach(rating.group_concepts(cards, AS_OF), REACH))
    assert ranked["forgotten"]["creatives"] == 2 and ranked["forgotten"]["verdict"] == "review"


def test_ads_not_opened_get_an_estimate_from_their_position_and_medium_reliability():
    partial = {key: REACH[key] for key in ("giant", "steady", "shop")}
    ranked = by_id(with_reach(rating.group_concepts(market(), AS_OF), partial))
    assert ranked["giant"]["reliability"] == "high"
    unread = ranked["forgotten"]
    assert unread["reliability"] == "medium" and unread["scale_basis"] == "impressions"
    assert unread["reach_per_day_estimate"] < ranked["shop"]["reach_per_day"]
    assert unread["verdict"] != "review"                 # an estimate is not enough to call it forgotten
    assert ranked["small"]["reach_per_day_estimate"] < unread["reach_per_day_estimate"] * 20


def test_without_reach_or_position_only_days_and_creatives_count():
    cards = [ad("1", started="2026-01-01"), ad("2", started="2026-06-25", body="Another text")]
    ranked = by_id(rating.group_concepts(cards, AS_OF))
    assert ranked["1"]["reliability"] == "low" and ranked["1"]["scale_basis"] is None
    assert ranked["1"]["score"] == 60.0 and ranked["1"]["verdict"] == "holding"
    assert ranked["2"]["verdict"] == "testing"
    switched_off = rating.evaluate(rating.group_concepts(market(), AS_OF), use_impressions=False)
    assert {item["reliability"] for item in switched_off} == {"low"}


def test_too_few_ads_with_reach_cannot_set_a_scale():
    ranked = by_id(with_reach(rating.group_concepts(market(), AS_OF), {"giant": 5_000_000, "shop": 98_000}))
    assert ranked["giant"]["reliability"] == "medium"


# --- the three searches saved from the live library -----------------------------------

def saved(name):
    data = json.loads((FIXTURES / f"rating_{name}.json").read_text(encoding="utf-8"))
    fetch = FetchResult(url="https://www.facebook.com/ads/library/?saved", outcome="ok", ads=data["cards"],
                        total_count=data["total_count"], source="structured")
    result = service.assemble(fetch, data["name"], data["spec"]["country"], as_of=date.fromisoformat(data["as_of"]))
    for item in result["ads"]:
        found = data["reach"].get(item["library_id"])
        if found:
            item["reach"] = {**found, "regions": []}
    signals.annotate(result["ads"])
    return result["ads"]


def named(ranked, name):
    return next(item for item in ranked if name in (item.get("advertiser") or ""))


def test_keyword_search_puts_the_ad_that_scales_first():
    ranked = saved("scarpe_da_corsa_it")
    scaling = named(ranked, "Zalando")
    assert ranked.index(scaling) < 3
    assert scaling["verdict"] == "scaling" and scaling["reliability"] == "high"
    assert scaling["reach_per_day"] > 100_000 and scaling["days_running"] < 60
    assert scaling["kind"] == "dynamic" and scaling["longevity_score"] < 70       # the earlier score had it eighth


def test_copies_of_one_video_no_longer_win():
    ranked = saved("scarpe_da_corsa_it")
    copied = named(ranked, "Cappellettoshop")
    assert copied["longevity_score"] == 100.0                 # first under the earlier score
    assert ranked.index(copied) >= 10 and copied["verdict"] == "average"
    assert (copied["creatives"], copied["cards"], copied["copies_total"]) == (1, 8, 80)
    assert copied["reach_per_day"] < 1_000 and copied["score_points"]["creative"] == 0.0


def test_long_running_ad_with_few_people_is_flagged_whatever_its_reuse():
    ranked = saved("scarpe_da_corsa_it")
    forgotten = named(ranked, "Gabrieli")
    assert forgotten["days_running"] > 500 and forgotten["reach_per_day"] < 100
    assert forgotten["creatives"] == 2 and forgotten["verdict"] == "review" and forgotten["reliability"] == "high"


def test_catalogue_ads_are_tagged_and_count_as_one_creative():
    ranked = saved("scarpe_da_corsa_it")
    feed = named(ranked, "HOKA")
    assert (feed["kind"], feed["creatives"], feed["cards"]) == ("catalog", 1, 8) and feed["products"] >= 2
    assert named(ranked, "Subito")["kind"] == "catalog"
    assert sum(item["verdict"] == "scaling" for item in ranked) <= 5


def test_company_translations_are_merged_and_the_top_is_not_a_tie():
    ranked = saved("kingshot_it")
    assert len(ranked) == 14                                   # 21 distinct texts before merging translations
    top = ranked[0]
    assert top["texts"] >= 4 and {"de", "en", "fr"} <= set(top["languages"])
    assert top["creatives"] < top["cards"] < top["copies_total"]
    scores = [item["score"] for item in ranked[:3]]
    assert scores == sorted(scores, reverse=True) and len(set(scores)) == 3
    assert all(item["longevity_score"] == 100.0 for item in ranked[:3])           # a three-way tie before
    verdicts = [item["verdict"] for item in ranked]
    assert 1 <= verdicts.count("scaling") <= 5 and "testing" in verdicts and "holding" in verdicts


def test_outside_the_eu_reach_is_shown_but_does_not_rate():
    ranked = saved("standing_desk_us")
    assert {item["reliability"] for item in ranked} == {"medium"}
    assert {item["scale_basis"] for item in ranked} == {"impressions"}
    european = [item for item in ranked if item.get("reach_per_day")]
    assert len(european) >= 10 and all(item["reach_in_market"] is False for item in european)
    assert all(item["score_weights"] == {"scale": 50, "staying": 30, "creative": 20} for item in ranked)
    assert ranked[0]["impression_rank"] <= 10 and ranked[0]["days_running"] >= 90
    flagged = [item for item in ranked if item["verdict"] == "review"]
    assert flagged and all(item["review"]["basis"] == "impressions" and item["days_running"] >= 90 for item in flagged)
