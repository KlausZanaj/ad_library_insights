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
    assert concept["creatives"] == 5 and concept["variant_ids"] and concept["score_parts"]["creative"] == 69.9
    many = rating.group_concepts([ad(str(n), video_url=f"https://v/{n}.mp4") for n in range(12)], AS_OF)[0]
    assert many["score_parts"]["creative"] == 100.0            # full at ten creatives, whatever the others have


def test_catalogue_ads_are_one_creative_with_products():
    feed = [ad(str(n), format="dpa", multiple_versions=True, headline=f"Product {n}", video_url=None,
               image_url=f"https://i/{n}.jpg") for n in range(6)]
    concept = rating.group_concepts(feed, AS_OF)[0]
    assert (concept["kind"], concept["creatives"], concept["products"], concept["cards"]) == ("catalog", 1, 6, 6)
    by_links = [ad(str(n), landing_url=f"https://shop.example/p/{n}", headline=f"Product {n}",
                   video_url=f"https://v/{n}.mp4") for n in range(6)]
    assert rating.group_concepts(by_links, AS_OF)[0]["kind"] == "catalog"      # same text, a product behind each ad
    tracked = [ad(str(n), landing_url=f"https://shop.example/desk?utm_content=v{n}", headline="The desk",
                  video_url=f"https://v/{n}.mp4") for n in range(6)]
    concept = rating.group_concepts(tracked, AS_OF)[0]         # one page with tracking tags is not a catalogue
    assert (concept["kind"], concept["creatives"]) == ("standard", 6)


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
    assert ranked["giant"]["score_weights"] == {"scale": 60, "staying": 25, "creative": 15}
    assert ranked["small"]["verdict"] == "average" and ranked["fresh"]["verdict"] == "testing"
    # the position alone never says that an ad scales or was forgotten
    assert not {"scaling", "review"} & {item["verdict"] for item in ranked.values()}


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
    assert ranked["1"]["score"] == 25.0 and ranked["1"]["verdict"] == "average"       # days only: nothing says it holds
    assert ranked["2"]["verdict"] == "testing"
    switched_off = rating.evaluate(rating.group_concepts(market(), AS_OF), use_impressions=False)
    assert {item["reliability"] for item in switched_off} == {"low"}


def test_an_ad_younger_than_a_week_is_only_ever_a_test():
    cards = market() + [ad("day-one", started="2026-06-29", body="Text of day-one", advertiser="day-one", impression_rank=7)]
    ranked = by_id(with_reach(rating.group_concepts(cards, AS_OF), {**REACH, "day-one": 900_000}))
    young = ranked["day-one"]
    assert young["days_running"] == 1 and young["reach_per_day"] == 128_571          # 900,000 over seven days, not one
    assert young["too_recent"] and young["verdict"] == "testing"
    assert ranked["giant"]["verdict"] == "scaling" and not ranked["giant"]["too_recent"]


def test_no_reach_in_the_searched_country_is_scale_zero_not_a_gap():
    ranked = rating.group_concepts(market(), AS_OF)
    for item in ranked:
        total = REACH[item["library_id"]]
        item["reach"] = {"available": True, "basis": "EU", "basis_total": total, "eu_total": total, "uk_total": None,
                         "country": "IT", "country_reach": 0 if item["library_id"] == "steady" else total,
                         "countries_reached": 3, "regions": []}
    ranked = by_id(signals.annotate(ranked))
    abroad = ranked["steady"]
    assert abroad["reach_total"] == 0 and abroad["reach_per_day"] == 0 and abroad["reliability"] == "high"
    assert abroad["score_parts"]["scale"] == 0.0 and abroad["verdict"] == "review"


def test_the_estimate_for_unread_ads_uses_reach_in_the_searched_country():
    ranked = rating.group_concepts(market(), AS_OF)
    for item in ranked:
        if item["library_id"] in ("giant", "steady", "shop"):
            total = REACH[item["library_id"]]
            item["reach"] = {"available": True, "basis": "EU", "basis_total": total * 10, "eu_total": total * 10,
                             "uk_total": None, "country": "IT", "country_reach": total, "countries_reached": 9,
                             "regions": []}
    ranked = by_id(signals.annotate(ranked))
    assert ranked["shop"]["reach_total"] == 98_000 and ranked["shop"]["reach"]["eu_total"] == 980_000
    unread = ranked["forgotten"]                       # position 4, right after shop: below 98,000 people, not 980,000
    assert unread["reach_per_day_estimate"] * unread["days_running"] < 98_000


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
        for other in item["variant_ids"]:                 # another ad of the same concept that was read
            if other in data["reach"]:
                item.setdefault("card_reach", {})[other] = data["reach"][other]
    signals.annotate(result["ads"], library_total=data["total_count"])
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
    european = [item for item in ranked if item.get("reach_elsewhere_per_day")]
    assert len(european) >= 10 and all(item["reach_in_market"] is False for item in european)
    assert not any("reach_per_day" in item or "reach_total" in item for item in ranked)
    assert all(item["score_weights"] == {"scale": 60, "staying": 25, "creative": 15} for item in ranked)
    assert ranked[0]["impression_rank"] <= 10 and ranked[0]["days_running"] >= 90
    assert {item["verdict"] for item in ranked} == {"holding", "average", "testing"}


# --- corrections checked on the saved searches ----------------------------------------

def position(ranked, library_id):
    return next(index for index, item in enumerate(ranked, 1) if item["library_id"] == library_id)


ONE_DAY_AD = "1318376673725569"        # Kingshot: 91,509 people in the EU on its first day, 476 of them in Italy


def test_scale_is_measured_in_the_searched_country_not_in_the_whole_eu():
    ranked = saved("kingshot_it")
    read = [item for item in ranked if item.get("reach", {}).get("available")]
    assert len(read) == 14
    for item in read:
        reach = item["reach"]
        assert item["reach_total"] == reach["country_reach"] < reach["eu_total"]
        assert item["reach_per_day"] == round(reach["country_reach"] / max(item["ad_days"], 7))
    top = ranked[0]
    assert (top["reach"]["eu_total"], top["reach_total"], top["reach_per_day"]) == (7_398_228, 835_709, 5_844)
    by_rate = sorted(read, key=lambda item: -item["reach_per_day"])
    assert [item["score_parts"]["scale"] for item in by_rate] == sorted((item["score_parts"]["scale"] for item in read), reverse=True)


def test_no_ad_younger_than_a_week_scales_or_holds():
    for name in ("kingshot_it", "scarpe_da_corsa_it", "standing_desk_us"):
        young = [item for item in saved(name) if item["days_running"] is not None and item["days_running"] < 7]
        assert young and all(item["verdict"] in ("testing", "ended") and item["too_recent"] for item in young)


def test_one_day_with_a_lot_of_reach_does_not_reach_the_top():
    # Right place: 13th of 14. One day of delivery is not a rate, and in Italy it reached 476 people.
    ranked = saved("kingshot_it")
    young = by_id(ranked)[ONE_DAY_AD]
    assert young["days_running"] == 1 and young["reach"]["eu_total"] == 91_509 and young["reach_total"] == 476
    assert young["reach_per_day"] == 68 and young["verdict"] == "testing"
    assert position(ranked, ONE_DAY_AD) == 13                  # it was fifth when the EU total over one day rated


def test_keyword_search_keeps_its_top_and_its_bottom():
    ranked = saved("scarpe_da_corsa_it")
    assert ranked[0]["advertiser"] == "Zalando"
    assert ranked.index(named(ranked, "Cappellettoshop")) >= 10


def test_search_without_reach_in_the_market_follows_the_list_of_the_library():
    # Right place: the order is Meta's impression order corrected by days and creatives, all at medium reliability.
    ranked = saved("standing_desk_us")
    assert [item["library_id"] for item in ranked[:5]] == ["1227451472671864", "2006807903279406", "1764904544497154",
                                                           "1621971626261673", "1451502250048330"]
    assert [item["score"] for item in ranked[:5]] == [91.1, 89.5, 81.2, 76.2, 73.5]
    assert [item["impression_rank"] for item in ranked[:5]] == [5, 1, 2, 11, 8]


# --- hard cases, each on real data, with the reason the position is right -------------

def test_hard_case_old_ad_with_few_people():
    # Right place: 37th of 106, "review". 516 days on air earn full staying power and little else:
    # 91 people a day is a thousand times fewer than the best ad, so it cannot sit near the top.
    ranked = saved("scarpe_da_corsa_it")
    old = named(ranked, "Gabrieli")
    assert (old["days_running"], old["reach_per_day"], old["reach_total"]) == (516, 91, 47_011)
    assert old["verdict"] == "review" and old["score_points"]["staying"] == 25.0 and old["score_points"]["scale"] < 1
    assert 30 <= ranked.index(old) + 1 <= 50


def test_hard_case_ad_shown_almost_only_outside_the_searched_country():
    # Right place: 12th of 14. 12,402 people in the EU, 966 of them in Italy over 53 days: for someone
    # studying Italy this is an ad of 18 people a day, whatever it does elsewhere.
    ranked = saved("kingshot_it")
    abroad = by_id(ranked)["2888031284866220"]
    assert abroad["reach"]["eu_total"] == 12_402 and abroad["reach_total"] == 966 and abroad["reach_per_day"] == 18
    assert position(ranked, "2888031284866220") == 12 and abroad["verdict"] == "average"
    assert abroad["creatives"] == 38 and abroad["score_points"]["scale"] < abroad["score_points"]["creative"]


def test_hard_case_search_without_any_reach_in_the_market():
    # Right place: nothing is rated "high". Reach read for the EU or the UK says nothing about the
    # United States, so every rating rests on the impression position and says so.
    ranked = saved("standing_desk_us")
    assert {item["reliability"] for item in ranked} == {"medium"}
    assert sum(1 for item in ranked if item.get("reach", {}).get("available")) == 19
    assert not {"scaling", "review"} & {item["verdict"] for item in ranked}      # neither can be told from a position
    assert not any("reach_per_day" in item or "reach_per_day_estimate" in item for item in ranked)


def test_hard_case_catalogue_ad():
    # Right place: 3rd of 106. Eight catalogue ads count as one creative (no creative points); it is
    # there for 176 days on air and 10,438 people a day, not for the number of products.
    ranked = saved("scarpe_da_corsa_it")
    feed = named(ranked, "HOKA")
    assert ranked.index(feed) == 2 and feed["kind"] == "catalog" and feed["verdict"] == "holding"
    assert (feed["cards"], feed["creatives"], feed["score_points"]["creative"]) == (8, 1, 0.0)
    assert (feed["days_running"], feed["reach_per_day"]) == (176, 10_438)


def test_hard_case_one_ad_in_several_languages():
    # Right place: one line at the top, not four. The German, English and French texts are the same ad;
    # counted apart they would fill the top of the table with copies of one idea.
    ranked = saved("kingshot_it")
    top = ranked[0]
    assert top["texts"] == 4 and {"de", "en", "fr"} <= set(top["languages"]) and top["cards"] == 58
    assert sum(1 for item in ranked if item["texts"] > 1) >= 2
    assert sum(item["texts"] for item in ranked) == 21 and len(ranked) == 14


def test_hard_case_small_shop_against_a_large_brand():
    # Right place: Zalando 1st (116,749 people a day), Cappellettoshop 18th (706 a day, one video copied
    # 80 times). Yet size alone does not decide: Flexora, 4,983 people a day for 112 days on five
    # creatives, sits above Decathlon's 15-day ad that reaches 102,421 a day.
    ranked = saved("scarpe_da_corsa_it")
    brand, shop = named(ranked, "Zalando"), named(ranked, "Cappellettoshop")
    assert (ranked.index(brand) + 1, ranked.index(shop) + 1) == (1, 18)
    assert brand["reach_per_day"] > 100 * shop["reach_per_day"] and shop["copies_total"] == 80 and shop["creatives"] == 1
    small, giant = named(ranked, "Flexora"), named(ranked, "Decathlon")
    assert small["reach_per_day"] < giant["reach_per_day"] / 20 and ranked.index(small) < ranked.index(giant)
    assert small["verdict"] == "holding" and giant["verdict"] == "scaling"


# --- what the independent review found, pinned ----------------------------------------

def test_an_ad_that_was_not_read_never_gains_from_it():
    # same days, same creatives, same people a day: the read ad and the estimated one score the same
    ranked = by_id(with_reach(rating.group_concepts(market(), AS_OF), {k: REACH[k] for k in ("giant", "steady", "shop")}))
    assert {item["score_weights"]["scale"] for item in ranked.values()} == {60}
    unread, read = ranked["forgotten"], ranked["shop"]
    assert unread["reliability"] == "medium" and read["reliability"] == "high"
    for item in ranked.values():
        assert item["score"] == pytest.approx(sum(item["score_points"].values()), abs=0.11) and 0 <= item["score"] <= 100


def test_position_scale_does_not_depend_on_how_much_of_the_list_was_loaded():
    cards = [ad(str(n), started="2026-01-01", body=f"Text {n}", advertiser=f"A{n}", impression_rank=n) for n in range(1, 41)]
    whole = by_id(signals.annotate(rating.group_concepts(cards, AS_OF), library_total=5_000))
    part = by_id(signals.annotate(rating.group_concepts(cards[:20], AS_OF), library_total=5_000))
    assert all(whole[key]["score"] == part[key]["score"] and whole[key]["verdict"] == part[key]["verdict"] for key in part)
    assert whole["1"]["score_parts"]["scale"] == 100.0 and 55 < whole["40"]["score_parts"]["scale"] < 60
    assert {item["verdict"] for item in whole.values()} == {"holding"}          # in the top 40 of 5,000 for six months


def test_close_rates_get_close_scales_and_the_lowest_is_not_zero():
    cards = [ad(name, started="2026-03-01", body=f"Text {name}", advertiser=name, impression_rank=rank)
             for rank, name in enumerate(("a", "b", "c"), start=1)]
    ranked = by_id(with_reach(rating.group_concepts(cards, AS_OF), {"a": 123_420, "b": 122_210, "c": 121_000}))
    scales = [ranked[name]["score_parts"]["scale"] for name in "abc"]
    assert scales[0] == 100.0 and min(scales) > 99                      # 1,020, 1,010 and 1,000 people a day
    assert {item["verdict"] for item in ranked.values()} == {"holding"}  # three ads: none is called forgotten


def test_scale_is_anchored_to_the_best_ad_not_to_the_weakest():
    ranked = saved("kingshot_it")
    before = {item["library_id"]: item["score_parts"]["scale"] for item in ranked}
    kept = [item for item in ranked if item["library_id"] not in ("1131624315910650", "2888031284866220")]
    after = {item["library_id"]: item["score_parts"]["scale"] for item in signals.annotate(kept, library_total=216)}
    assert all(after[key] == before[key] for key in after)             # dropping the two weakest moves nobody


def test_reach_of_a_concept_adds_up_the_ads_that_were_read():
    # Flexora runs one text as five ads; two were read: 201,059 people in 112 days and 184,905 in 58
    ranked = saved("scarpe_da_corsa_it")
    concept = named(ranked, "Flexora")
    assert (concept["cards"], concept["reach_cards_read"], concept["reach_total"]) == (5, 2, 385_964)
    assert concept["reach_per_day"] == round(201_059 / 112 + 184_905 / 58) == 4_983
    assert concept["reach"]["country_reach"] == 201_059                # the detail still shows the most shown ad


def test_cards_are_read_in_the_order_of_the_library_three_per_concept_at_most():
    cards = [ad(f"z{n}", body="One text", advertiser="Big", impression_rank=n, video_url=f"https://v/{n}.mp4") for n in range(1, 6)]
    cards += [ad("old", started="2025-01-01", body="Old text", advertiser="Small", impression_rank=6),
              ad("new", started="2026-06-28", body="New text", advertiser="Other", impression_rank=7)]
    ranked = rating.group_concepts(cards, AS_OF)
    chosen = [card for _, card in rating.cards_to_read(ranked, 5)]
    assert chosen == ["z1", "z2", "z3", "old", "new"]                  # not z4, z5: three of one concept are enough
    assert [card for _, card in rating.cards_to_read(ranked, 2)] == ["z1", "z2"]


def test_a_concept_with_a_fresh_ad_is_not_called_forgotten():
    cards = market() + [ad(f"x{n}", started="2026-02-01", body=f"Extra {n}", advertiser=f"x{n}", impression_rank=8 + n)
                        for n in range(3)]
    cards.append(ad("forgotten-new", started="2026-06-10", body="Text of forgotten", advertiser="forgotten",
                    impression_rank=20, video_url="https://v/new.mp4"))
    reach = {**REACH, "x0": 300_000, "x1": 250_000, "x2": 200_000}
    with_new = by_id(with_reach(rating.group_concepts(cards, AS_OF), reach))["forgotten"]
    assert with_new["days_running"] == 545 and with_new["newest_days"] == 20 and with_new["verdict"] != "review"
    without = by_id(with_reach(rating.group_concepts(cards[:-1], AS_OF), reach))["forgotten"]
    assert without["newest_days"] == 545 and without["verdict"] == "review"


def test_a_large_total_reach_is_never_called_forgotten():
    # SPORT LIFE: 629 days, 257 people a day, but 161,736 people in all, among the larger totals of the search
    ranked = saved("scarpe_da_corsa_it")
    old = named(ranked, "SPORT LIFE")
    assert (old["days_running"], old["reach_per_day"], old["reach_total"]) == (629, 257, 161_736)
    assert old["score_parts"]["scale"] <= 25 and old["verdict"] == "average"
    assert named(ranked, "Subito")["verdict"] == "holding"             # 899 days, 2.7 million people


def test_scaling_is_for_ads_between_two_weeks_and_three_months():
    ranked = saved("scarpe_da_corsa_it")
    scaling = [item for item in ranked if item["verdict"] == "scaling"]
    assert {item["advertiser"] for item in scaling} == {"Zalando", "Decathlon Italia"}
    assert all(14 <= item["days_running"] < 90 and item["reliability"] == "high" for item in scaling)
    assert named(ranked, "SHEIN")["verdict"] == "testing"              # 13 days: one day short


def test_ended_ads_are_labelled_as_such():
    cards = market() + [ad("gone", started="2026-03-17", body="Text of gone", advertiser="gone", impression_rank=7,
                           ended="2026-03-19")]
    ranked = by_id(rating.group_concepts(cards, AS_OF))
    assert ranked["gone"]["verdict"] == "ended" and ranked["gone"]["days_running"] == 2
    still = rating.group_concepts([ad("a", started="2026-01-01", ended="2026-02-01", impression_rank=2),
                                   ad("b", started="2026-03-01", impression_rank=1)], AS_OF)[0]
    assert still["verdict"] != "ended" and still["days_running"] == 180        # one of its ads is still on air


def test_texts_are_not_merged_on_a_guessed_language():
    same_picture = [ad("1", body="Order today on shop.example.com and save", image_url="https://i/a.jpg", video_url=None),
                    ad("2", body="The desk your back was waiting for", image_url="https://i/a.jpg", video_url=None)]
    assert len(rating.group_concepts(same_picture, AS_OF)) == 2          # two English texts on one picture
    one_digit = [ad("1", body="Solo oggi 8 euro di sconto sulla scrivania", video_url="https://v/a.mp4"),
                 ad("2", body="Desk 8 XL", video_url="https://v/b.mp4")]
    assert len(rating.group_concepts(one_digit, AS_OF)) == 2             # a shared digit is not a translation
    variants = [ad("1", body="New desk released! 🎮🚀", video_url="https://v/a.mp4"),
                ad("2", body="New desk available! 🎮🚀", video_url="https://v/b.mp4")]
    assert len(rating.group_concepts(variants, AS_OF)) == 2              # same words: two versions, one language


def test_keyword_match_is_a_hint():
    assert rating.matches_query({"body": "La scrivania regolabile per chi lavora da casa"}, "Scrivania regolabile")
    assert rating.matches_query({"body": "", "headline": "Caffè in grani"}, "caffe")
    assert not rating.matches_query({"body": "I refused the offer for three years"}, "standing desk")


def test_reach_figures_that_are_not_numbers_do_not_break_the_rating():
    ranked = rating.group_concepts(market(), AS_OF)
    ranked[0]["reach"] = {"available": True}
    ranked[1]["reach"] = {"available": True, "country": "IT", "country_reach": float("nan"), "eu_total": -5}
    ranked[2]["reach"] = {"available": True, "country": "ALL", "eu_total": 700_000, "uk_total": 300_000}
    rated = signals.annotate(ranked)
    assert all(0 <= item["score"] <= 100 for item in rated)
    assert signals.market_total({"available": True, "country": None, "eu_total": 700_000, "uk_total": 300_000}) == 1_000_000
