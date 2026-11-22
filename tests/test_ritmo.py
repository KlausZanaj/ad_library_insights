"""Ritmo: STA/LTA launch pace, two-sided Page CUSUM format drift, and Little's Law."""
import math
from datetime import date, timedelta

from ad_library_insights import history, packs
from ad_library_insights.lab import ritmo

AS_OF = date(2026, 11, 13)


def _concept(cid: str, days_ago: int, media_type: str = "image", status: str = "active", **extra) -> dict:
    started = (AS_OF - timedelta(days=days_ago)).isoformat()
    return {
        "library_id": cid,
        "started": started,
        "media_type": media_type,
        "status": status,
        "days_running": max(1, days_ago),
        **extra,
    }


def _snap(taken_at: str, ads: list[dict], *, loaded_share: float = 1.0, mode: str = "company") -> dict:
    return {
        "subject": {"key": "company:IT:99", "mode": mode, "label": "Acme", "country": "IT", "page_id": "99"},
        "taken_at": taken_at,
        "active_ads": len(ads),
        "ads_loaded": len(ads),
        "loaded_share": loaded_share,
        "ads": ads,
    }


# --- Fail-closed gates ---------------------------------------------------------------


def test_ritmo_fails_closed_on_keyword_partial_list_and_insufficient_history():
    concepts = [_concept(str(i), i * 3) for i in range(12)]
    kw = ritmo.analyze(concepts, mode="keyword", loaded_share=1.0, as_of=AS_OF)
    assert kw["available"] is False and kw["reason"] == "keyword_mode" and kw["trigger_ai"] is False

    partial = ritmo.analyze(concepts, mode="company", loaded_share=0.55, as_of=AS_OF)
    assert partial["available"] is False and partial["reason"] == "partial_list"

    tiny = ritmo.analyze([_concept("1", 2)], mode="company", loaded_share=1.0, as_of=AS_OF)
    assert tiny["available"] is False and tiny["reason"] == "insufficient_history"

    empty = ritmo.analyze_snapshots([], as_of=AS_OF)
    assert empty["available"] is False and empty["reason"] == "no_snapshots"


# --- STA/LTA 1w vs 8w ----------------------------------------------------------------


def test_sta_lta_steady_spike_slowdown_burst_and_large_n():
    # Steady pace: 3 launches in STA (0..6d) and 3 in each of prior 8 weeks (24 total LTA)
    steady = [_concept(f"sta{i}", i) for i in range(3)]
    for w in range(1, 9):
        for j in range(3):
            steady.append(_concept(f"w{w}_{j}", w * 7 + j))
    st_res = ritmo.sta_lta(steady, as_of=AS_OF, survivor_bias=True)
    assert st_res["measurable"] is True
    assert len(st_res["weeks"]) == 9 and st_res["weeks"][-1]["is_sta"] is True
    assert st_res["sta_count"] == 3 and st_res["lta_total"] == 24 and st_res["lta_mean"] == 3.0
    assert st_res["state"] == "steady" and st_res["trigger_ai"] is False

    # Active-only stricter threshold vs full-cohort threshold:
    # 4 launches in STA vs 0.5/wk LTA (total 4 LTA, N=8, p=0.0056): blocked by min_count=5 under active_only, spike under full
    borderline = [_concept(f"s{i}", i) for i in range(4)] + [
        _concept(f"b{w}", w * 14) for w in range(1, 5)
    ]
    active_gate = ritmo.sta_lta(borderline, as_of=AS_OF, survivor_bias=True)
    full_gate = ritmo.sta_lta(borderline, as_of=AS_OF, survivor_bias=False)
    assert active_gate["trigger_ai"] is False
    assert full_gate["state"] == "spike" and full_gate["trigger_ai"] is True and len(full_gate["recent_ids"]) == 4

    # Real spike under active_only: 8 launches in STA vs 2/wk LTA -> ratio 4.0, p <= 0.01
    lta_2wk = [_concept(f"b{w}_{j}", w * 7 + j) for w in range(1, 9) for j in range(2)]
    spike = [_concept(f"sp{i}", i % 6) for i in range(8)] + lta_2wk
    sp_res = ritmo.sta_lta(spike, as_of=AS_OF, survivor_bias=True)
    assert sp_res["state"] == "spike" and sp_res["trigger_ai"] is True
    assert sp_res["p_value"] < 0.01 and len(sp_res["recent_ids"]) == 5

    # Genuine slowdown: 0 launches in STA vs 4/wk LTA (32 LTA, (8/9)^32 = 0.023 < 0.05)
    slow = [_concept(f"sl{w}_{j}", w * 7 + j) for w in range(1, 9) for j in range(4)]
    sl_res = ritmo.sta_lta(slow, as_of=AS_OF, survivor_bias=False)
    assert sl_res["state"] == "slowdown" and sl_res["trigger_ai"] is False

    # Burst from near-zero baseline: LTA total < 4 but strong STA burst
    burst = [_concept(f"bu{i}", i % 5) for i in range(6)]
    bu_res = ritmo.sta_lta(burst, as_of=AS_OF, survivor_bias=True)
    assert bu_res["measurable"] is True and bu_res["state"] == "spike" and bu_res["ratio"] is None

    # Log-space binomial stability on N > 2000 (no OverflowError / NaN)
    huge_p = ritmo._binom_upper_tail(3000, 500, 1.0 / 9.0)
    assert math.isfinite(huge_p) and 0.0 <= huge_p <= 1e-6


# --- Format CUSUM --------------------------------------------------------------------


def test_format_cusum_detects_slow_up_and_down_drifts_without_single_ad_false_alarms():
    # Steady interleaved ~30% video, ~70% image across 20 concepts over 50 days -> no drift
    steady = [
        _concept(f"s{i}", 50 - i * 2, media_type=("video" if i % 3 == 0 else "image"))
        for i in range(20)
    ]
    st_cu = ritmo.format_cusum(steady, as_of=AS_OF)
    assert st_cu["measurable"] is True and st_cu["drift_detected"] is False and st_cu["trigger_ai"] is False

    # Upward slow drift: baseline 3/10 (30%) video -> recent 9/10 (90%) video
    up = [_concept(f"ub{i}", 58 - i * 3, media_type=("video" if i in (1, 5, 8) else "image")) for i in range(10)]
    up += [_concept(f"ur{i}", 28 - i * 2, media_type=("image" if i == 0 else "video")) for i in range(10)]
    up_cu = ritmo.format_cusum(up, as_of=AS_OF)
    assert up_cu["measurable"] is True and up_cu["drift_detected"] is True and up_cu["trigger_ai"] is True
    assert up_cu["primary"]["format"] == "video" and up_cu["primary"]["direction"] == "up"
    assert up_cu["primary"]["changepoint_date"] is not None
    assert len(up_cu["example_ids"]) == 3

    # Downward drift: baseline 8/10 (80%) image -> recent 2/10 (20%) image
    down = [_concept(f"db{i}", 58 - i * 3, media_type=("video" if i in (2, 7) else "image")) for i in range(10)]
    down += [_concept(f"dr{i}", 28 - i * 2, media_type=("image" if i in (0, 3) else "video")) for i in range(10)]
    dw_cu = ritmo.format_cusum(down, as_of=AS_OF)
    assert dw_cu["drift_detected"] is True and any(f["direction"] == "down" for f in dw_cu["formats"])

    # Single stray video from 0% baseline: material excess < 2.5 -> NO false alarm!
    stray = [_concept(f"z{i}", 50 - i * 2, media_type="image") for i in range(19)]
    stray.append(_concept("stray_vid", 2, media_type="video"))
    stray_cu = ritmo.format_cusum(stray, as_of=AS_OF)
    assert stray_cu["drift_detected"] is False and stray_cu["trigger_ai"] is False

    # Short span gate (< 14 days)
    clustered = [_concept(f"c{i}", 5, media_type="image") for i in range(18)]
    short = ritmo.format_cusum(clustered, as_of=AS_OF)
    assert short["measurable"] is False and short["reason"] == "short_span"

    # Same-day batch across formats must NOT trigger false CUSUM drift by library_id ordering
    same_day_batch = (
        [_concept(f"10{i}", 30, media_type="image") for i in range(8)]
        + [_concept(f"20{i}", 30, media_type="video") for i in range(8)]
        + [_concept("301", 5, media_type="video")]
    )
    batch_cu = ritmo.format_cusum(same_day_batch, as_of=AS_OF)
    assert batch_cu["measurable"] is False and batch_cu["reason"] == "clustered_dates"
    assert batch_cu["drift_detected"] is False and batch_cu["trigger_ai"] is False

    # Mixed naive / Z / offset-aware snapshot timestamps must not crash merge_snapshot_concepts
    mixed_snaps = [
        _snap("2026-10-01T10:00:00", [_concept("m1", 10)]),
        _snap("2026-10-22T10:00:00Z", [_concept("m1", 31), _concept("m2", 2)]),
    ]
    _, _, span_days = ritmo.merge_snapshot_concepts(mixed_snaps)
    assert span_days == 21


# --- Little's Law --------------------------------------------------------------------


def test_littles_law_implied_and_durata_cross_check_and_gates():
    # 12 active concepts, 7 launched in last 28d (2,6,10,14,18,22,26) -> lambda = 7/28 = 0.25/day = 1.75/wk -> W = 48d
    active = [_concept(f"a{i}", 2 + i * 4) for i in range(12)]
    lt_imp = ritmo.littles_law(active, active, as_of=AS_OF)
    assert lt_imp["measurable"] is True and lt_imp["steady_state_checked"] is False
    assert lt_imp["lambda_per_week"] == 1.75 and lt_imp["implied_mean_days"] == 48.0
    assert lt_imp["balance_state"] == "implied_only"

    # Cross-checked with Durata RMST: balanced (~48d), accumulating (rmst=20 -> exp=5 vs 12 -> 2.4x),
    # ramping_or_cutting (rmst=80 -> exp=20 vs 12 -> 0.6x)
    bal = ritmo.littles_law(active, active, as_of=AS_OF, durata_report={"available": True, "rmst_days": 45.0})
    acc = ritmo.littles_law(active, active, as_of=AS_OF, durata_report={"available": True, "rmst_days": 20.0})
    cut = ritmo.littles_law(active, active, as_of=AS_OF, durata_report={"available": True, "rmst_days": 80.0})
    assert bal["steady_state_checked"] is True and bal["balance_state"] == "balanced"
    assert acc["balance_state"] == "accumulating" and cut["balance_state"] == "ramping_or_cutting"

    assert ritmo.littles_law(active[:3], active, as_of=AS_OF)["reason"] == "too_few_active"
    old_only = [_concept(f"old{i}", 50 + i) for i in range(6)]
    assert ritmo.littles_law(old_only, old_only, as_of=AS_OF)["reason"] == "too_few_launches"


def test_littles_law_aligns_active_count_with_durata_cohort_window():
    # Steady account: 30 evergreen concepts active for 200d + 1 launch/day lasting 10d (10 active + 18 ended in 28d)
    evergreen = [_concept(f"ev{i}", 200) for i in range(30)]
    recent_active = [_concept(f"ra{i}", i) for i in range(10)]
    recent_ended = [_concept(f"re{i}", 10 + i, ended_after=10) for i in range(18)]
    active_list = evergreen + recent_active
    all_list = active_list + recent_ended

    out = ritmo.littles_law(
        active_list,
        all_list,
        as_of=AS_OF,
        durata_report={"available": True, "rmst_days": 10.0, "window_days": 90},
    )
    assert out["steady_state_checked"] is True
    assert out["active_concepts"] == 10
    assert out["active_concepts_total"] == 40
    assert out["cohort_window_days"] == 90
    assert out["expected_active"] == 10.0
    assert out["balance_ratio"] == 1.0
    assert out["balance_state"] == "balanced"


# --- Snapshot merging, History integration & Pack isolation --------------------------


def test_snapshot_merge_and_history_preserve_summary_and_reduce_survivor_bias(tmp_path):
    store = history.History(tmp_path)
    # Earlier snapshot 30 days ago carried concepts that stopped since, plus ongoing concepts
    early_ads = [
        _concept(f"e{i}", 35 + i, media_type="image", ids=[f"e{i}", f"ev{i}"])
        for i in range(6)
    ] + [_concept("shared1", 40, media_type="image", ids=["shared1"])]
    recent_ads = [_concept("shared1", 40, media_type="image", ids=["shared1"])] + [
        _concept(f"r{i}", 2 + i % 4, media_type="video", ids=[f"r{i}"]) for i in range(6)
    ]
    res1 = {"country": "IT", "mode": "company", "page": {"page_id": "99", "name": "Acme"},
            "fetched_at": "2026-10-14T10:00:00+00:00", "ads_parsed": len(early_ads),
            "signals": {"active_ads": len(early_ads)}, "ads": early_ads}
    res2 = {"country": "IT", "mode": "company", "page": {"page_id": "99", "name": "Acme"},
            "fetched_at": "2026-11-13T10:00:00+00:00", "ads_parsed": len(recent_ads),
            "signals": {"active_ads": len(recent_ads)}, "ads": recent_ads}

    first = store.record(res1)
    assert first == {"available": False, "reason": "first_search", "subject": first["subject"], "snapshots": 1}
    second = store.record(res2)
    # summary() shape must stay exact for backward compatibility
    assert set(history.summary(second)) == {"available", "key", "previous_taken_at", "days_between", "counts", "survival"}
    assert second["ritmo"]["available"] is True
    assert second["ritmo"]["source"] == "snapshots"
    assert second["ritmo"]["survivor_bias"] is False
    assert second["ritmo"]["snapshot_span_days"] == 30
    assert store.ritmo("company:IT:99")["available"] is True


def test_packs_isolate_ritmo_to_testing_slice_only():
    concepts = [_concept(f"c{i}", 50 - i * 2, media_type=("video" if i >= 12 else "image")) for i in range(20)]
    report = ritmo.analyze(concepts, mode="company", loaded_share=1.0, as_of=AS_OF)
    assert report["available"] is True

    result = {
        "mode": "company",
        "country": "IT",
        "page": {"page_id": "99", "name": "Acme"},
        "ads_parsed": len(concepts),
        "distinct_ads": len(concepts),
        "ads": [{**c, "score": 50.0, "verdict": "holding", "reliability": "medium",
                 "longevity_score": 40.0, "creatives": 1, "cards": 1, "copies_total": 1} for c in concepts],
        "signals": {
            "active_ads": len(concepts), "ads_loaded": len(concepts), "concepts": len(concepts),
            "distinct_texts": len(concepts), "video_share": 0.4, "new_per_week": 2.0,
            "started_last_30_days": 8, "share_started_last_30_days": 0.4,
            "weekly_launches": [{"week_start": "2026-11-02", "ads": 2}],
            "verdicts": {"holding": len(concepts)}, "reliability": {"medium": len(concepts)},
            "needs_review": 0, "platforms": [], "buttons": [], "destinations": [], "languages": [],
            "format_share": {"video": 0.4, "image": 0.6},
            "copy_patterns": {"texts_analyzed": len(concepts), "reused_texts": [], "repeated_openers": [],
                              "hook_types": {}, "common_structures": {}, "share_with_proof": 0.0,
                              "share_with_urgency": 0.0, "share_mentioning_offer": 0.0,
                              "share_mentioning_price": 0.0},
            "reach": {"checked_ads": 0, "available": False, "note": ""},
            "audience": None,
        },
        "ritmo": report,
    }
    slices, _ = packs.sections(result, ads=3, frames=False)
    assert "## Pace and format drift (Ritmo)" in slices["testing"]
    assert "Launch pace (STA/LTA, 1w vs prior 8w)" in slices["testing"]
    for other in ("overview", "copy", "creative", "reach"):
        assert "Ritmo" not in slices[other]
        assert "STA/LTA" not in slices[other]
        assert "CUSUM" not in slices[other]
