"""Annunci fuori schema: deterministic selection of cross-signal paradox concepts."""
from ad_library_insights import packs
from ad_library_insights.lab import anomalie


def _ad(lib_id: str, *, days: int = 30, rpd: int | None = 500, body: str | None = None,
        creatives: int = 2, rank: int = 10, media_type: str = "video", verdict: str = "holding") -> dict:
    default_body = (
        "Discover why ergonomic acoustic felt desk dividers transform open-plan offices into quiet, "
        "focused studios without heavy renovation work or permanent wall mounting. Free swatches shipped weekly."
    )
    return {
        "library_id": lib_id,
        "advertiser": "Studio Quiet",
        "days_running": days,
        "reach_per_day": rpd,
        "reach_total": rpd * max(days, 7) if rpd is not None else None,
        "body": default_body if body is None else body,
        "creatives": creatives,
        "impression_rank": rank,
        "media_type": media_type,
        "verdict": verdict,
        "status": "inactive" if verdict == "ended" else "active",
        "score": 55.0,
        "reliability": "high" if rpd is not None else "medium",
        "longevity_score": 40.0,
        "cards": 1,
        "copies_total": 1,
    }


def test_anomalie_gates_clean_account_all_five_rules_cap_and_pack_isolation():
    too_few = anomalie.select([_ad("1"), _ad("2"), _ad("3")])
    assert too_few["available"] is False and too_few["reason"] == "too_few_concepts"

    clean_ads = [_ad(f"ok{i}", days=30, rpd=500, creatives=2) for i in range(6)]
    clean = anomalie.select(clean_ads, mode="company")
    assert clean["available"] is True and clean["status"] == "none" and clean["items"] == []

    # Build a rich set triggering ALL 5 contradiction rules alongside steady baseline peers
    peers = [_ad(f"p{i}", days=30, rpd=500, creatives=2, rank=10 + i) for i in range(6)]
    paradoxes = [
        _ad("p_long_low", days=90, rpd=40, creatives=2),          # rule 1: long live, tiny reach
        _ad("p_fast_boom", days=8, rpd=2400, creatives=2),         # rule 2: <21d breakout reach
        _ad("p_tiny_copy", days=32, rpd=1800, body="Order now."),  # rule 3: high reach, tiny copy
        _ad("p_many_low", days=28, rpd=60, creatives=8),           # rule 4: many creatives, low reach
        _ad("p_single_cr", days=120, rpd=1900, creatives=1),       # rule 5: long live, 1 creative, top reach
    ]
    res = anomalie.select(peers + paradoxes, mode="company")
    assert res["available"] is True and res["status"] == "flagged"
    assert len(res["items"]) == anomalie.MAX_ANOMALIES
    # Diversity priority picks distinct kinds first
    picked_kinds = {item["kind"] for item in res["items"]}
    assert len(picked_kinds) == 4

    # Single-creative rule also works when reach is absent via impression_rank (e.g. non-EU keyword search)
    no_reach_peers = [_ad(f"nr{i}", days=25, rpd=None, creatives=2, rank=10 + i) for i in range(6)]
    no_reach_anom = _ad("nr_single", days=95, rpd=None, creatives=1, rank=1)
    kw_res = anomalie.select(no_reach_peers + [no_reach_anom], mode="keyword")
    assert kw_res["sample_scope"] == "keyword_sample"
    assert any(
        item["library_id"] == "nr_single" and item["kind"] == "long_live_single_creative_top_rank"
        for item in kw_res["items"]
    )

    # Verify pack isolation: reach.md and copy.md get Out-of-pattern ads, overview/creative/testing do not
    pack_in = {
        "mode": "company",
        "country": "IT",
        "page": {"page_id": "44", "name": "Studio Quiet"},
        "ads_parsed": len(peers + paradoxes),
        "distinct_ads": len(peers + paradoxes),
        "ads": peers + paradoxes,
        "signals": {
            "active_ads": len(peers + paradoxes), "ads_loaded": len(peers + paradoxes),
            "concepts": len(peers + paradoxes), "distinct_texts": len(peers + paradoxes),
            "video_share": 1.0, "new_per_week": 1.0, "started_last_30_days": 5,
            "share_started_last_30_days": 0.4, "weekly_launches": [{"week_start": "2026-11-02", "ads": 1}],
            "verdicts": {"holding": len(peers + paradoxes)}, "reliability": {"high": len(peers + paradoxes)},
            "needs_review": 0, "platforms": [], "buttons": [], "destinations": [], "languages": [],
            "format_share": {"video": 1.0},
            "copy_patterns": {"texts_analyzed": 10, "reused_texts": [], "repeated_openers": [],
                              "hook_types": {}, "common_structures": {}, "share_with_proof": 0.0,
                              "share_with_urgency": 0.0, "share_mentioning_offer": 0.0,
                              "share_mentioning_price": 0.0},
            "reach": {"checked_ads": 11, "available": True, "ads_with_reach": 11, "ads_with_market_reach": 11,
                      "median_reach_per_day": 500, "highest_reach_per_day": 2400,
                      "median_reach_total": 15000, "highest_reach_total": 40000, "top_countries": []},
            "audience": None,
        },
        "anomalie": res,
    }
    slices, _ = packs.sections(pack_in, ads=3, frames=False)
    assert "## Out-of-pattern ads (Annunci fuori schema)" in slices["reach"]
    assert "## Out-of-pattern ads (Annunci fuori schema)" in slices["copy"]
    for untouched in ("overview", "creative", "testing"):
        assert "Out-of-pattern ads" not in slices[untouched]
        assert "Annunci fuori schema" not in slices[untouched]
