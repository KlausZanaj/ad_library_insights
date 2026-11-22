"""Su cosa si regge: reach concentration, NCD copy families, Shannon diversity, Pianka overlap and JS drift."""
import math

import pytest

from ad_library_insights import compare, history, packs
from ad_library_insights.lab import struttura


def _ad(lib_id: str, reach_total: int | None = None, *, body: str = "", media_type: str = "video",
        domain: str = "store.example", days: int = 30, eu_total: int | None = None,
        uk_total: int | None = None, breakdown_3d: list[dict] | None = None,
        cards_read: int = 1, cards: int = 1) -> dict:
    reach = {"available": any(v is not None for v in (reach_total, eu_total, uk_total, breakdown_3d))}
    if eu_total is not None:
        reach["eu_total"] = eu_total
    if uk_total is not None:
        reach["uk_total"] = uk_total
    if breakdown_3d is not None:
        reach["breakdown_3d"] = breakdown_3d
    return {
        "library_id": lib_id,
        "advertiser": "Acme Co",
        "body": body,
        "media_type": media_type,
        "landing_domain": domain,
        "days_running": days,
        "creatives": 1,
        "cards": cards,
        "copies_total": cards,
        "reach_cards_read": cards_read,
        "reach_total": reach_total,
        "reach_per_day": round(reach_total / max(days, 7)) if reach_total is not None else None,
        "reach": reach,
        "score": 60.0,
        "verdict": "holding",
        "reliability": "high" if reach_total is not None else "medium",
        "longevity_score": 40.0,
    }


def test_reach_concentration_concentrated_balanced_eu_fallback_and_gate():
    few = [_ad("1", 1000), _ad("2", 500)]
    assert struttura.reach_concentration(few)["measurable"] is False

    # Concentrated: top 1 holds 80% of 100,000
    conc = [_ad("1", 80000), _ad("2", 10000), _ad("3", 5000), _ad("4", 3000), _ad("5", 2000)]
    c_res = struttura.reach_concentration(conc, country="IT")
    assert c_res["measurable"] is True and c_res["scope"] == "market"
    assert c_res["level"] == "concentrated" and c_res["top1_share"] == 0.8 and c_res["top3_share"] == 0.95
    assert c_res["effective_n"] < 2.0 and c_res["gini"] > 0.55 and c_res["leaders"][0]["library_id"] == "1"

    # Balanced across 5 concepts: exact equality -> gini = 0.0, norm_hhi = 0.0, effective_n = 5.0
    bal = [_ad(f"b{i}", 2000) for i in range(5)]
    b_res = struttura.reach_concentration(bal, country="DE")
    assert b_res["level"] == "balanced" and b_res["gini"] == 0.0
    assert b_res["normalized_hhi"] == 0.0 and b_res["effective_n"] == 5.0

    # EU+UK fallback when searched country reach is absent
    eu_only = [_ad(f"e{i}", None, eu_total=(4000 if i == 0 else 1000), uk_total=0) for i in range(4)]
    fb = struttura.reach_concentration(eu_only, country="US")
    assert fb["measurable"] is True and fb["scope"] == "eu_uk" and fb["top1_share"] == round(4000 / 7000, 3)

    # In-market reads including zero-reach ads must not silently fall back to EU+UK
    mixed_zero = [_ad("m1", 1000, eu_total=5000), _ad("m2", 0, eu_total=5000), _ad("m3", 0, eu_total=5000), _ad("m4", 0, eu_total=5000)]
    for ad in mixed_zero:
        ad["reach_in_market"] = True
    mz = struttura.reach_concentration(mixed_zero, country="IT")
    assert mz["measurable"] is True and mz["scope"] == "market" and mz["concepts_with_reach"] == 4

    too_few_in_market = [_ad("z1", 1000, eu_total=5000), _ad("z2", 0, eu_total=5000)]
    for ad in too_few_in_market:
        ad["reach_in_market"] = True
    extra = [_ad("z3", None, eu_total=5000), _ad("z4", None, eu_total=5000)]
    no_fb = struttura.reach_concentration(too_few_in_market + extra, country="IT")
    assert no_fb["measurable"] is False and no_fb["reason"] == "too_few_with_reach"


def test_copy_families_counts_concepts_without_library_id_and_js_drift_handles_mixed_timestamps():
    tpl = "Compact insulated steel bottle keeps water cold for 24 hours on trails and daily commutes."
    ads = [_ad("", body=f"{tpl} Variant A"), _ad("", body=f"{tpl} Variant B"), _ad("", body=f"{tpl} Variant C"), _ad("id4", body="Completely separate espresso roast copy delivered fresh every week.")]
    cf = struttura.copy_families(ads)
    assert cf["measurable"] is True and cf["top_families"][0]["size"] == 3 and cf["largest_family_share"] == 0.75

    snaps = [
        {"taken_at": "2026-10-01T10:00:00", "audience_distribution": {"ads_with_breakdown": 1, "cells": [{"country": "IT", "age_range": "25-34", "gender": "male", "reach": 100}]}},
        {"taken_at": "2026-10-15T10:00:00Z", "audience_distribution": {"ads_with_breakdown": 1, "cells": [{"country": "IT", "age_range": "25-34", "gender": "female", "reach": 100}]}},
    ]
    js = struttura.audience_js_drift(snaps)
    assert js["measurable"] is True and js["days_between"] == 14.0


def test_copy_families_ncd_clustering_symmetry_gate_and_cap():
    assert struttura.copy_families([_ad("1", body="Short copy.")])["measurable"] is False

    # Check raw-DEFLATE NCD symmetry
    bx = b"upgrade your studio lighting in seconds with warm glare free optics and magnetic mount"
    by = b"upgrade your studio lighting in seconds with cool glare free optics and magnetic mount"
    bz = b"artisanal roasted espresso beans delivered fresh every Friday morning directly from Genoa"
    assert struttura._ncd(bx, by, struttura._deflate_len(bx), struttura._deflate_len(by)) == \
        struttura._ncd(by, bx, struttura._deflate_len(by), struttura._deflate_len(bx))
    assert struttura._ncd(bx, by, struttura._deflate_len(bx), struttura._deflate_len(by)) <= struttura.NCD_THRESHOLD
    assert struttura._ncd(bx, bz, struttura._deflate_len(bx), struttura._deflate_len(bz)) > struttura.NCD_THRESHOLD

    base_tpl = (
        "Transform your daily reading nook with our solid walnut task lamp built for flicker-free "
        "evening focus, touch dimming across three warm tones, and free five-year hardware support. "
        "Save {pct}% on your first order today while studio stock lasts."
    )
    alt_tpl = (
        "Why do ceramic pour-over drippers retain heat longer than thin glass cones? Compare our "
        "double-walled stoneware brewer tested across eighty specialty coffee bars nationwide, "
        "complete with precision flow control and dishwasher-safe glaze."
    )
    alt_two = (
        "Traveling across three time zones without wrinkled linen shirts starts with our compact "
        "cedar-lined garment folder engineered for overhead cabin bins, ultra-lightweight ripstop "
        "seams, and lifetime zipper replacement coverage."
    )
    ads = [
        _ad("t1", body=base_tpl.format(pct="15")),
        _ad("t2", body=base_tpl.format(pct="20") + " https://shop.example/utm"),
        _ad("t3", body=base_tpl.format(pct="25")),
        _ad("a1", body=alt_tpl),
        _ad("a2", body=alt_two),
    ]
    cf = struttura.copy_families(ads)
    assert cf["measurable"] is True and cf["evaluated"] == 5
    # The three tweaked template ads collapse into one 3-member family -> 3 distinct families total
    assert cf["families_count"] == 3 and cf["top_families"][0]["size"] == 3
    assert cf["top_families"][0]["representative_id"] == "t1" and cf["largest_family_share"] == 0.6

    # Verify MAX_NCD_CONCEPTS cap
    many = [_ad(f"m{i}", body=f"{alt_tpl} Extra variation phrase number {i} for catalog testing.") for i in range(65)]
    capped = struttura.copy_families(many)
    assert capped["capped"] is True and capped["evaluated"] == 60 and capped["total_with_text"] == 65


def test_shannon_diversity_monopoly_vs_uniform():
    monopoly = [_ad(f"m{i}", media_type="video", domain="only.example") for i in range(5)]
    sh_m = struttura.shannon_diversity(monopoly)
    assert sh_m["formats"]["measurable"] is True and sh_m["formats"]["entropy_bits"] == 0.0
    assert sh_m["formats"]["effective_k"] == 1.0 and sh_m["formats"]["evenness"] == 0.0
    assert sh_m["formats"]["label"] == "concentrated"

    balanced = [
        _ad("b1", media_type="video", domain="a.example"),
        _ad("b2", media_type="video", domain="b.example"),
        _ad("b3", media_type="image", domain="a.example"),
        _ad("b4", media_type="image", domain="b.example"),
    ]
    sh_b = struttura.shannon_diversity(balanced)
    assert sh_b["formats"]["entropy_bits"] == 1.0 and sh_b["formats"]["effective_k"] == 2.0
    assert sh_b["formats"]["evenness"] == 1.0 and sh_b["formats"]["label"] == "balanced"
    assert sh_b["destinations"]["entropy_bits"] == 1.0


def test_pianka_overlap_identical_disjoint_partial_and_compare_wiring():
    bd_a = [
        {"country": "IT", "age_range": "25-34", "male": 300, "female": 500, "unknown": 0},
        {"country": "IT", "age_range": "35-44", "male": 100, "female": 100, "unknown": 0},
    ]
    bd_disjoint = [
        {"country": "DE", "age_range": "55-64", "male": 900, "female": 100, "unknown": 0},
    ]
    bd_part = [
        {"country": "IT", "age_range": "25-34", "male": 100, "female": 200, "unknown": 0},
        {"country": "IT", "age_range": "45-54", "male": 500, "female": 200, "unknown": 0},
    ]
    res_a = {"page": {"name": "Alpha"}, "country": "IT", "signals": {
        "active_ads": 5, "distinct_texts": 5, "new_per_week": 1.0, "started_last_30_days": 2,
        "share_started_last_30_days": 0.4, "verdicts": {"holding": 2}, "needs_review": 0,
        "video_share": 0.5, "format_share": {"video": 0.5, "image": 0.5}, "languages": [],
        "copy_patterns": {"share_with_proof": 0.5, "share_mentioning_offer": 0.2},
        "reach": {"available": False}, "audience": None, "platforms": [], "buttons": [], "destinations": [],
    }, "ads": [_ad("a1", 5000, breakdown_3d=bd_a)]}
    res_same = {**res_a, "page": {"name": "Beta"}, "ads": [_ad("b1", 4000, breakdown_3d=bd_a)]}
    res_dis = {**res_a, "page": {"name": "Gamma"}, "ads": [_ad("g1", 4000, breakdown_3d=bd_disjoint)]}
    res_part = {**res_a, "page": {"name": "Delta"}, "ads": [_ad("d1", 4000, breakdown_3d=bd_part)]}
    res_none = {**res_a, "page": {"name": "Empty"}, "ads": [_ad("n1", 4000, breakdown_3d=None)]}

    assert struttura.pianka_overlap(res_a, res_none)["measurable"] is False
    same = struttura.pianka_overlap(res_a, res_same)
    assert same["measurable"] is True and same["overlap"] == 1.0 and same["band"] == "high"
    disjoint = struttura.pianka_overlap(res_a, res_dis)
    assert disjoint["overlap"] == 0.0 and disjoint["band"] == "low"
    partial = struttura.pianka_overlap(res_a, res_part)
    assert 0.3 < partial["overlap"] < 0.7 and partial["distinct_a"] and partial["distinct_b"]

    cmp_out = compare.compare(res_a, res_same)
    assert [r["key"] for r in cmp_out["rows"]] == [k for _, k, _ in compare.ROWS]
    assert cmp_out["audience_overlap"]["overlap"] == 1.0


def test_audience_js_drift_and_history_wiring(tmp_path):
    def _res_snap(taken_at: str, bd: list[dict], lib_id: str) -> dict:
        return {
            "country": "IT",
            "mode": "company",
            "page": {"page_id": "77", "name": "Studio Nord"},
            "fetched_at": taken_at,
            "ads_parsed": 1,
            "signals": {"active_ads": 1},
            "ads": [_ad(lib_id, 2000, breakdown_3d=bd, body="Sample desk lamp ad copy with more than thirty chars.")],
        }

    store = history.History(tmp_path)
    s1 = _res_snap("2026-10-14T10:00:00+00:00", [{"country": "IT", "age_range": "25-34", "male": 800, "female": 200, "unknown": 0}], "1")
    s2 = _res_snap("2026-10-20T10:00:00+00:00", [{"country": "IT", "age_range": "25-34", "male": 800, "female": 200, "unknown": 0}], "1")
    s3 = _res_snap("2026-11-13T10:00:00+00:00", [{"country": "DE", "age_range": "45-54", "male": 100, "female": 900, "unknown": 0}], "2")

    assert store.record(s1)["available"] is False
    same_changes = store.record(s2)
    assert set(history.summary(same_changes)) == {"available", "key", "previous_taken_at", "days_between", "counts", "survival"}
    assert same_changes["audience_drift"]["state"] == "stable" and same_changes["audience_drift"]["js_distance"] == 0.0

    shifted_changes = store.record(s3)
    drift = shifted_changes["audience_drift"]
    assert drift["measurable"] is True and drift["state"] == "shifted" and drift["js_distance"] >= 0.8
    assert drift["top_gainers"][0]["age_range"] == "45-54" and drift["top_losers"][0]["age_range"] == "25-34"


def test_packs_isolate_struttura_to_reach_and_copy_only():
    tpl = "Compact insulated steel bottle keeps water cold for 24 hours on trails and daily commutes. Variant #{i}."
    ads = [_ad(f"c{i}", 10000 if i == 0 else 1000, body=tpl.format(i=i)) for i in range(5)]
    report = struttura.analyze(ads, mode="keyword", country="IT")
    result = {
        "mode": "keyword",
        "query": "steel bottle",
        "country": "IT",
        "ads_parsed": 5,
        "distinct_ads": 5,
        "ads": ads,
        "signals": {
            "active_ads": 5, "ads_loaded": 5, "concepts": 5, "distinct_texts": 5,
            "video_share": 1.0, "new_per_week": 1.0, "started_last_30_days": 5,
            "share_started_last_30_days": 1.0, "weekly_launches": [{"week_start": "2026-11-02", "ads": 5}],
            "verdicts": {"holding": 5}, "reliability": {"high": 5}, "needs_review": 0,
            "platforms": [], "buttons": [], "destinations": [{"domain": "store.example", "ads": 5, "share": 1.0}],
            "languages": [], "format_share": {"video": 1.0},
            "copy_patterns": {"texts_analyzed": 5, "reused_texts": [], "repeated_openers": [],
                              "hook_types": {}, "common_structures": {}, "share_with_proof": 0.0,
                              "share_with_urgency": 0.0, "share_mentioning_offer": 0.0,
                              "share_mentioning_price": 0.0},
            "reach": {"checked_ads": 5, "available": True, "ads_with_reach": 5, "ads_with_market_reach": 5,
                      "median_reach_per_day": 100, "highest_reach_per_day": 500,
                      "median_reach_total": 1000, "highest_reach_total": 10000, "top_countries": []},
            "audience": None,
        },
        "struttura": report,
    }
    slices, _ = packs.sections(result, ads=3, frames=False)
    assert "## Account structure (Su cosa si regge)" in slices["reach"]
    assert "keyword sample across advertisers" in slices["reach"]
    assert "## Copy families (Su cosa si regge)" in slices["copy"]
    assert "NCD zlib" in slices["copy"]
    for untouched in ("overview", "creative", "testing"):
        assert "Su cosa si regge" not in slices[untouched]
        assert "Gini" not in slices[untouched]
        assert "NCD zlib" not in slices[untouched]
