from datetime import date

from ad_library_insights import parser, scoring

AS_OF = date(2026, 4, 5)


def ad(library_id, started, body, advertiser="A", copies=1, ended=None):
    return {"library_id": library_id, "started": started, "ended": ended, "body": body,
            "advertiser": advertiser, "copies": copies}


def test_fingerprint_ignores_case_punctuation_and_emoji():
    assert scoring.text_fingerprint("Raise your desk!  \U0001F680") == scoring.text_fingerprint("raise YOUR desk")
    assert scoring.text_fingerprint("Raise your desk") != scoring.text_fingerprint("Lower your desk")
    assert scoring.text_fingerprint(" \U0001F680 ") == ""


def test_days_running_uses_end_date_when_inactive():
    assert scoring.days_running(ad("1", "2026-01-05", "x"), AS_OF) == 90
    assert scoring.days_running(ad("1", "2026-01-05", "x", ended="2026-01-15"), AS_OF) == 10
    assert scoring.days_running(ad("1", None, "x"), AS_OF) is None


def test_score_bounds_and_weights():
    assert scoring.longevity_score(0, 1) == 0.0
    assert scoring.longevity_score(90, 1) == 60.0
    assert scoring.longevity_score(900, 10) == 100.0
    assert scoring.longevity_score(None, 10) == 40.0
    assert scoring.longevity_score(45, 1) == 30.0
    assert scoring.longevity_score(45, 1, horizon_days=45) == 60.0


def test_repetitions_sum_counters_across_cards_with_same_copy():
    ranked = scoring.rank_ads([
        ad("1", "2026-03-01", "Same copy", copies=2),
        ad("2", "2026-02-01", "same copy!", copies=3),
        ad("3", "2026-03-01", "Same copy", advertiser="B"),  # another advertiser: separate
    ], as_of=AS_OF)
    merged = next(a for a in ranked if a["advertiser"] == "A")
    assert merged["library_id"] == "2"  # the oldest card represents the group
    assert merged["repetitions"] == 5 and merged["creative_variants"] == 2
    assert merged["variant_ids"] == ["1"]
    assert next(a for a in ranked if a["advertiser"] == "B")["repetitions"] == 1
    assert len(ranked) == 2


def test_ranking_order_older_and_more_repeated_first():
    ranked = scoring.rank_ads([
        ad("new", "2026-04-01", "fresh"),
        ad("old", "2026-01-01", "evergreen"),
        ad("mid-cloned", "2026-03-01", "cloned", copies=10),
        ad("old-tie", "2025-12-01", "evergreen two"),
    ], as_of=AS_OF)
    assert [a["library_id"] for a in ranked] == ["mid-cloned", "old-tie", "old", "new"]
    assert ranked[0]["longevity_score"] > ranked[1]["longevity_score"] == ranked[2]["longevity_score"]


def test_without_collapsing_every_card_is_kept():
    ranked = scoring.rank_ads([ad("1", "2026-03-01", "x"), ad("2", "2026-03-02", "x")],
                              as_of=AS_OF, collapse_duplicates=False)
    assert len(ranked) == 2 and all(a["repetitions"] == 2 for a in ranked)


def test_ads_without_body_are_never_merged():
    ranked = scoring.rank_ads([ad("1", "2026-03-01", ""), ad("2", "2026-03-01", "")], as_of=AS_OF)
    assert len(ranked) == 2


def test_ranks_parsed_cards_end_to_end(cards):
    ranked = scoring.rank_ads(parser.parse_cards(cards), as_of=AS_OF)
    assert [a["library_id"] for a in ranked] == ["1001", "1002"]
    assert ranked[0]["repetitions"] == 2 and ranked[0]["variant_ids"] == ["1003"]
