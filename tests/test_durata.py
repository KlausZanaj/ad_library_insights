"""Tests for Durata cohort survival analysis (Kaplan-Meier, Weibull, Lindy) and testing slice output."""
from datetime import date, timedelta

import pytest

from ad_library_insights import packs, rating
from ad_library_insights.lab import durata

AS_OF = date(2026, 6, 30)


def _concept(idx: int, days_ago: int, ended_after: int | None = None, status: str | None = None,
             started: str | None = None) -> dict:
    start_dt = AS_OF - timedelta(days=days_ago)
    start_str = started if started is not None else start_dt.isoformat()
    ended_str = (start_dt + timedelta(days=ended_after)).isoformat() if ended_after is not None else None
    is_ended = ended_after is not None or status == "inactive"
    return {
        "library_id": f"c{idx}",
        "started": start_str,
        "ended": ended_str,
        "status": status or ("inactive" if is_ended else "active"),
        "days_running": ended_after if ended_after is not None else days_ago,
        "score": 50.0,
        "verdict": "ended" if is_ended else "average",
        "reliability": "medium",
        "creatives": 1,
        "cards": 1,
        "media_type": "video",
        "body": f"Concept text {idx}",
    }


def test_kaplan_meier_matches_hand_verified_curve_ci_and_rmst():
    obs = [(5, True), (5, True), (10, False), (15, True), (20, False)]
    km = durata.kaplan_meier(obs)
    assert km["max_observed"] == 20
    assert km["median_reached"] is True and km["median_days"] == 15.0
    assert len(km["steps"]) == 2

    s1, s2 = km["steps"]
    assert s1["day"] == 5 and s1["at_risk"] == 5 and s1["ended"] == 2
    assert s1["survival"] == 0.6
    # Greenwood SE at t=5: 0.6 * sqrt(2 / (5 * 3)) = 0.2191
    assert s1["se"] == 0.2191
    assert 0.0 < s1["ci_low"] < s1["survival"] < s1["ci_high"] < 1.0

    assert s2["day"] == 15 and s2["at_risk"] == 2 and s2["ended"] == 1
    assert s2["survival"] == 0.3
    assert durata.survival_at(km["steps"], 4, 20) == 1.0
    assert durata.survival_at(km["steps"], 10, 20) == 0.6
    assert durata.survival_at(km["steps"], 25, 20) is None
    # Area: 1.0*5 + 0.6*10 + 0.3*5 = 12.5
    assert km["rmst_days"] == 12.5


def test_kaplan_meier_median_midpoint_and_unreached_median():
    midpoint = durata.kaplan_meier([(10, True), (20, True), (30, True), (40, False)])
    # S(10)=0.75, S(20)=0.50 (exact 0.5 with next step at t=30) -> (20+30)/2 = 25.0
    assert midpoint["median_reached"] is True and midpoint["median_days"] == 25.0

    no_next = durata.kaplan_meier([(10, True), (20, True), (30, False), (40, False)])
    assert no_next["median_reached"] is True and no_next["median_days"] == 20.0

    unreached = durata.kaplan_meier([(5, True), (10, False), (15, False), (20, False)])
    assert unreached["median_reached"] is False and unreached["median_days"] is None


def test_weibull_mle_distinguishes_regimes_and_rejects_degenerate_inputs():
    # Early cut (k < 0.85): sharp infant mortality on days 1-3, long tail survivors to day 90
    early = [(1, True)] * 6 + [(2, True)] * 4 + [(3, True)] * 2 + [(85, False)] * 8
    w_early = durata.weibull_mle(early)
    assert w_early and w_early["shape_k"] < 0.85 and w_early["regime"] == "early_cut"

    # Constant hazard (exponential k ~= 1.0) built from theoretical survival S = exp(-t / 30)
    steady = [
        (3, True), (7, True), (11, True), (16, True), (21, True),
        (28, True), (36, True), (48, True), (65, True),
        (70, False), (80, False), (90, False),
    ]
    w_steady = durata.weibull_mle(steady)
    assert w_steady and 0.85 <= w_steady["shape_k"] <= 1.15 and w_steady["regime"] == "steady_turnover"

    # Fatigue decay (k > 1.15): very few early cuts, rising hazard between days 35 and 55
    fatigue = [(35, True), (38, True), (42, True), (45, True), (48, True), (52, True), (55, True)] + [(60, False)] * 5
    w_fatigue = durata.weibull_mle(fatigue)
    assert w_fatigue and w_fatigue["shape_k"] > 1.15 and w_fatigue["regime"] == "fatigue_decay"

    # Too few events or all events at max observed duration -> None
    assert durata.weibull_mle([(5, True)] * 4 + [(20, False)] * 10) is None
    assert durata.weibull_mle([(10, True)] * 6 + [(10, False)] * 5) is None


def test_lindy_conditional_survival_respects_risk_and_horizon_gates():
    obs = (
        [(5, True)] * 4
        + [(16, False), (20, True), (25, False), (35, False), (40, True), (50, False), (60, False), (75, False)]
    )
    km = durata.kaplan_meier(obs)
    rows = durata.lindy_conditional(km["steps"], obs, km["max_observed"])
    assert rows and [r["after_days"] for r in rows] == [14, 30]
    for row in rows:
        s_age = durata.survival_at(km["steps"], row["after_days"], km["max_observed"])
        s_next = durata.survival_at(km["steps"], row["after_days"] + 30, km["max_observed"])
        assert row["still_active_share"] == round(s_next / s_age, 4)

    # Fewer than 5 concepts at risk or max_observed < 44 -> None
    short = [(5, True)] * 5 + [(25, False)] * 6
    assert durata.lindy_conditional(durata.kaplan_meier(short)["steps"], short, 25) is None

    # Concepts ending ON age=14 must not count as at-risk past day 14
    ended_on_age = [(14, True)] * 5 + [(50, False)] + [(5, True)] * 4
    assert durata.lindy_conditional(durata.kaplan_meier(ended_on_age)["steps"], ended_on_age, 50) is None


def test_analyze_treats_future_ended_date_as_active_at_as_of():
    cohort = [_concept(i, 30, ended_after=40 if i < 4 else None) for i in range(6)]
    cohort += [_concept(10 + i, 35, ended_after=10) for i in range(4)]
    report = durata.analyze(cohort, mode="company", active_status="all", loaded_share=1.0, as_of=AS_OF)
    assert report["available"] is True
    assert report["active_in_window"] == 6 and report["ended_in_window"] == 4
    assert report["max_observed_days"] == 30


def test_analyze_quality_gates_fail_closed():
    cohort = [_concept(i, 30 + i * 4, ended_after=5 + i if i < 5 else None) for i in range(12)]
    assert durata.analyze(cohort, mode="keyword", active_status="all")["reason"] == "keyword_mode"
    assert durata.analyze(cohort, mode="company", active_status="active")["reason"] == "active_only"
    partial = durata.analyze(cohort, mode="company", active_status="all", loaded_share=0.6)
    assert partial["available"] is False and partial["reason"] == "partial_list"

    unverified = durata.analyze(cohort, mode="company", active_status="all", loaded_share=None, as_of=AS_OF)
    assert unverified["available"] is False and unverified["reason"] == "partial_list"
    assert "completeness unverified" in "\n".join(durata.format_summary(unverified))

    too_few = durata.analyze(cohort[:8], mode="company", active_status="all", loaded_share=1.0, as_of=AS_OF)
    assert too_few["available"] is False and too_few["reason"] == "too_few_concepts"

    too_few_ended = [_concept(i, 40, ended_after=5 if i < 2 else None) for i in range(12)]
    out = durata.analyze(too_few_ended, mode="company", active_status="all", loaded_share=1.0, as_of=AS_OF)
    assert out["available"] is False and out["reason"] == "too_few_ended"


def test_analyze_window_filtering_exclusions_and_same_day_duration():
    concepts = [_concept(i, 20 + i * 5, ended_after=3 + i if i < 5 else None) for i in range(10)]
    concepts.append(_concept(90, 120, ended_after=10))                              # outside 90d window
    concepts.append(_concept(91, 30, ended_after=None, status="inactive"))          # missing ended date
    concepts.append(_concept(92, 10, ended_after=-2))                               # invalid negative range
    concepts.append(_concept(93, 15, ended_after=0))                                # same-day stop -> min 1 day
    concepts.append(_concept(94, 40, started=""))                                   # missing started date

    report = durata.analyze(concepts, mode="company", active_status="all", loaded_share=0.95,
                            window_days=90, as_of=AS_OF)
    assert report["available"] is True
    assert report["outside_window"] == 1
    assert report["excluded_undated"] == 2
    assert report["excluded_invalid"] == 1
    assert report["concepts_in_window"] == 11
    assert report["ended_in_window"] == 6 and report["active_in_window"] == 5
    assert report["fastest_ended"][0]["library_id"] == "c93" and report["fastest_ended"][0]["days"] == 1


def test_format_summary_and_packs_isolation_in_testing_slice_only():
    concepts = [_concept(i, 20 + i * 6, ended_after=4 + i * 3 if i < 6 else None) for i in range(12)]
    report = durata.analyze(concepts, mode="company", active_status="all", loaded_share=1.0,
                            window_days=90, as_of=AS_OF)
    lines = durata.format_summary(report)
    assert 5 <= len(lines) <= 10
    text = "\n".join(lines)
    assert "Median lifespan (Kaplan-Meier):" in text
    assert "not profit or ROAS" in text

    unavail_lines = durata.format_summary(durata.analyze(concepts, mode="keyword", active_status="all"))
    assert "NOT MEASURABLE (keyword_mode)" in unavail_lines[0]

    ranked = rating.group_concepts([
        {"library_id": c["library_id"], "started": c["started"], "ended": c["ended"],
         "status": c["status"], "advertiser": "Northwind", "body": c["body"], "copies": 1,
         "media_type": "video", "format": "video"}
        for c in concepts
    ], AS_OF)
    result = {
        "mode": "company",
        "country": "IT",
        "fetched_at": "2026-06-30T10:00:00+00:00",
        "ads_parsed": len(ranked),
        "distinct_ads": len(ranked),
        "page": {"name": "Northwind"},
        "signals": {
            "active_ads": len(ranked), "ads_loaded": len(ranked), "new_per_week": 1.0,
            "started_last_30_days": 2, "share_started_last_30_days": 0.17, "weekly_launches": [],
            "verdicts": {"average": 6, "ended": 6}, "needs_review": 0, "platforms": [], "buttons": [],
            "destinations": [], "format_share": {"video": 1.0}, "languages": [],
            "copy_patterns": {"texts_analyzed": 12, "hook_types": {}, "common_structures": {},
                              "share_with_proof": 0, "share_with_urgency": 0, "share_mentioning_offer": 0,
                              "share_mentioning_price": 0, "reused_texts": [], "repeated_openers": []},
            "reach": {"available": False, "note": "No reach"},
        },
        "ads": ranked,
        "durata": report,
    }
    slices, _ = packs.sections(result, ads=5, frames=False)
    assert "## Duration and survival (cohort)" in slices["testing"]
    assert "Median lifespan (Kaplan-Meier):" in slices["testing"]
    assert "Duration and survival" not in slices["overview"]
    assert "Median lifespan" not in slices["overview"]


def test_durata_flags_small_sample_under_20_ended_concepts():
    small_cohort = [_concept(i, 20 + i, ended_after=5 + (i % 6)) for i in range(12)]
    small_rep = durata.analyze(small_cohort, mode="company", active_status="all", loaded_share=1.0, as_of=AS_OF)
    assert small_rep["available"] is True and small_rep["small_sample"] is True
    assert "small sample" in "\n".join(durata.format_summary(small_rep))

    large_cohort = [_concept(i, 20 + (i % 40), ended_after=5 + (i % 12)) for i in range(22)]
    large_rep = durata.analyze(large_cohort, mode="company", active_status="all", loaded_share=1.0, as_of=AS_OF)
    assert large_rep["available"] is True and large_rep["small_sample"] is False
    assert "small sample" not in "\n".join(durata.format_summary(large_rep))
