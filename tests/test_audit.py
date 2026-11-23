"""Tests for deterministic warning-only report auditing (`lab.audit` and MCP `check_report`)."""
import asyncio
import json
from pathlib import Path

import pytest
from fastmcp import Client

from ad_library_insights import briefs, server
from ad_library_insights.lab import audit


def _sample_result(*, has_reach: bool = True, too_recent: bool = False) -> dict:
    ad1 = {
        "library_id": "882123034940286",
        "advertiser": "Acme Co",
        "body": "Durable desk for home office",
        "headline": "Acme Desk",
        "cta": "Shop now",
        "landing_domain": "acme.example",
        "started": "2026-08-01",
        "days_running": 90,
        "ad_days": 90,
        "too_recent": too_recent,
        "verdict": "scaling" if not too_recent else "average",
        "reliability": "high" if has_reach else "medium",
        "score": 88.0,
        "creatives": 4,
        "cards": 4,
        "copies_total": 4,
        "media_type": "video",
        "reach_per_day": 1400 if has_reach else None,
        "reach_total": 126000 if has_reach else None,
        "reach_in_market": has_reach,
        "members": [{"library_id": "882123034940999"}],
    }
    return {
        "mode": "company",
        "country": "IT",
        "fetched_at": "2026-11-22T10:00:00+00:00",
        "ads_parsed": 1,
        "distinct_ads": 1,
        "page": {"page_id": "111222333", "name": "Acme Co"},
        "signals": {
            "active_ads": 1, "ads_loaded": 1, "new_per_week": 0.5,
            "started_last_30_days": 0, "share_started_last_30_days": 0.0, "weekly_launches": [],
            "verdicts": {"scaling": 1} if not too_recent else {"average": 1}, "needs_review": 0,
            "platforms": [], "buttons": [], "destinations": [],
            "format_share": {"video": 1.0}, "languages": [],
            "copy_patterns": {"texts_analyzed": 1, "hook_types": {}, "common_structures": {},
                              "share_with_proof": 0, "share_with_urgency": 0, "share_mentioning_offer": 0,
                              "share_mentioning_price": 0, "reused_texts": [], "repeated_openers": []},
            "reach": {
                "available": has_reach,
                "country": "IT",
                "ads_with_market_reach": 1 if has_reach else 0,
                "ads_with_reach": 1 if has_reach else 0,
                "median_reach_per_day": 1400 if has_reach else None,
                "median_reach_total": 126000 if has_reach else None,
                "note": "No reach",
            },
        },
        "ads": [ad1],
    }


def _project_card() -> dict:
    # Price 122, VAT 22% (net 100), cost 30, shipping 5, IT (+3% Meta fee) -> margin 65, cpa 63.11, roas 1.93
    return {
        "product": "Standing desk",
        "price": 122.0,
        "product_cost": 30.0,
        "market": "IT",
        "goal": "10 orders a day",
        "main_problem": "High CPA",
        "vat_pct": 22.0,
        "shipping_cost": 5.0,
    }


def test_clean_italian_and_english_reports_pass_with_zero_warnings(tmp_path):
    pack = briefs.prepare("plan", _sample_result(), ads=1, project=_project_card(), lang="it", directory=tmp_path)
    folder = Path(pack["folder"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["audit"]["project_numbers"]["cpa"] == 63.11
    assert manifest["audit"]["project_numbers"]["roas"] == 1.93

    good_it = """
# Standing desk: piano contro Acme Co, IT

| | |
|---|---:|
| Margine netto per ordine | 65 |
| CPA di pareggio | 63,11 |
| ROAS di pareggio | 1,93 |
| Primo giro (5 annunci) | 788,9 |
| Regola di spegnimento: 126,22 - 189,33 | |

### Idea 1: Gancio diretto
- **Prende da:** domanda iniziale (annuncio 882123034940286, 1.400 persone al giorno).
- **Round 2:** i vincitori di round 1 vengono scalati senza toccare il budget di test.
- La sopravvivenza non è misurabile da una sola ricerca: nessuna spesa competitor è pubblica.
"""
    res_it = audit.check_report(folder, good_it)
    assert res_it["ok"] is True and res_it["status"] == "ok" and res_it["blocking"] is False
    assert res_it["warning_count"] == 0

    good_en = """
# Standing desk: plan against Acme Co, IT

- Margin per order: 65
- Break-even CPA: 63.11 · Break-even ROAS: 1.93x
- Round 1: 5 ads, up to 788.90 in total (5 ads at 157.78 per ad: 157.78 per ad stays below cap)
- Cut: an ad that has spent 126.22 to 189.33 with no sale.
- Borrows from scaling pattern (ad 882123034940999: 1,400 people per day).
- Survival is NOT MEASURABLE yet; Meta publishes no spend for competitors.
"""
    res_en = audit.check_report(folder, good_en)
    assert res_en["status"] == "ok" and res_en["warning_count"] == 0


def test_audit_flags_hallucinated_ids_too_recent_winners_math_drift_and_banned_claims(tmp_path):
    res_data = _sample_result(has_reach=False, too_recent=True)
    pack = briefs.prepare("plan", res_data, ads=1, project=_project_card(), lang="it", directory=tmp_path)
    folder = Path(pack["folder"])

    flawed = """
- Margine netto per ordine: 92
- Break-even CPA: 80.00
- Break-even ROAS: 1.58x
- Primo giro: fino a 500 €
- Cut rule: stop at 200 to 300
- Riprende da ad vincente 882123034940286 e da 999999999999999 (top ad, 2,100 people per day).
- The competitor spends €4,000 a day and has a cut rate of 45% in week 1.
"""
    out = audit.check_report(folder, flawed)
    assert out["status"] == "warnings" and out["blocking"] is False
    codes = {w["code"] for w in out["warnings"]}
    assert {
        "unknown_ad_id",
        "too_recent_cited_as_winner",
        "project_number_mismatch",
        "reach_claimed_without_data",
        "forbidden_competitor_claim",
        "unmeasured_survival_claim",
    } <= codes
    mismatched_fields = {w["field"] for w in out["warnings"] if w["code"] == "project_number_mismatch"}
    assert {"margin", "cpa", "roas", "round_total", "cut_low", "cut_high"} <= mismatched_fields

    # Same too-recent ID WITH explicit caveat + negated reach/spend lines stays warning-free
    clean_caveat = """
- Ad 882123034940286 is too recent to judge (< 7 days): describe only, do not treat as holding.
- Reach is not published in US and Meta does not publish competitor spend; survival is not measurable.
"""
    clean_out = audit.check_report(folder, clean_caveat)
    assert clean_out["status"] == "ok" and clean_out["warning_count"] == 0


def test_check_report_mcp_tool_supports_report_path_and_handles_missing_pack(tmp_path):
    pack = briefs.prepare("analysis", _sample_result(), ads=1, lang="en", directory=tmp_path)
    report_file = tmp_path / "draft.md"
    report_file.write_text("Top concept 882123034940286 and phantom id 123456789012345.", encoding="utf-8")

    async def run():
        async with Client(server.mcp) as client:
            ok_res = (await client.call_tool("check_report", {
                "pack_folder": pack["folder"],
                "report_path": str(report_file),
            })).data
            err_res = (await client.call_tool("check_report", {
                "pack_folder": str(tmp_path / "missing-pack"),
                "report_text": "hello",
            })).data
            return ok_res, err_res

    ok_res, err_res = asyncio.run(run())
    assert ok_res["ok"] is True and ok_res["blocking"] is False
    assert ok_res["warning_count"] == 1 and ok_res["warnings"][0]["id"] == "123456789012345"
    assert err_res["ok"] is False and "manifest.json" in err_res["error"]


def test_audit_single_cut_threshold_and_contextual_12digit_id_rules(tmp_path):
    pack = briefs.prepare("plan", _sample_result(), ads=1, project=_project_card(), lang="it", directory=tmp_path)
    folder = Path(pack["folder"])

    # Single-threshold cut lines + 12-digit non-ID order code must NOT produce false alarms
    clean = """
- Cut rule: switch off at 2x CPA (126.22).
- Regola di spegnimento: 189,33 €.
- Reference order number 123456789012 and ad 882123034940286.
"""
    res_clean = audit.check_report(folder, clean)
    assert res_clean["status"] == "ok" and res_clean["warning_count"] == 0

    # Wrong single cut + wrong one-sided range + contextual 12-digit IDs (table cell, URL, prefixed id) + 15-digit bare ID
    bad = """
- Cut rule: switch off at 2x CPA (500).
- Cut rule: spend 126.22 to 999 before stopping.
| 1 | 123456789012 | Video |
- https://www.facebook.com/ads/library/?id=234567890123
- Compare with id 345678901234 and 999888777666555.
"""
    res_bad = audit.check_report(folder, bad)
    assert res_bad["status"] == "warnings"
    unknown = {w["id"] for w in res_bad["warnings"] if w["code"] == "unknown_ad_id"}
    assert unknown == {"123456789012", "234567890123", "345678901234", "999888777666555"}
    cut_fields = [w["field"] for w in res_bad["warnings"] if w["code"] == "project_number_mismatch"]
    assert "cut_rule" in cut_fields and "cut_high" in cut_fields and "cut_low" not in cut_fields
