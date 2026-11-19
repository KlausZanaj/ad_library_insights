"""Tests for Prova prima di spendere: real margin, Italy +3% fee, max CPC, Poisson stop odds and Level 3 pack."""
import math
import pytest

from ad_library_insights import breakeven, briefs, project
from ad_library_insights.lab import precheck

BASE_CARD = {
    "product": "Standing desk",
    "price": 349.0,
    "product_cost": 120.0,
    "market": "DE",
    "goal": "30 orders a day",
    "main_problem": "High cost per purchase",
}


def test_base_economics_match_breakeven_cpa_without_extra_costs():
    out = precheck.analyze(price=60, product_cost=25, market="DE")
    assert out["net_margin"] == breakeven.breakeven_cpa(60, 25) == 35.0
    assert out["ad_fee_pct"] == 0.0
    assert out["cpa_ads"] == 35.0
    assert out["has_real_costs"] is False


def test_real_costs_and_italy_meta_fee_adjust_cpa_downward():
    # VAT 22% on 122 -> net 100.00; (100 - 35) * 0.90 = 58.50;
    # minus shipping 6.00, 2% payment fee on 122 (2.44) + 0.30, other 1.00 = 48.76
    out = precheck.analyze(
        price=122.0,
        product_cost=35.0,
        market="IT",
        vat_pct=22.0,
        shipping_cost=6.0,
        payment_fee_pct=2.0,
        payment_fee_fixed=0.30,
        return_rate_pct=10.0,
        other_costs=1.0,
    )
    assert out["net_price"] == 100.0
    assert out["net_margin"] == 48.76
    assert out["ad_fee_pct"] == 3.0
    assert out["cpa_ads"] == round(48.76 / 1.03, 2)
    assert out["has_real_costs"] is True

    it_simple = precheck.analyze(price=60, product_cost=25, market="it")
    assert it_simple["cpa_ads"] == round(35.0 / 1.03, 2) == 33.98

    overridden = precheck.analyze(price=60, product_cost=25, market="IT", ad_fee_pct=0.0)
    assert overridden["ad_fee_pct"] == 0.0 and overridden["cpa_ads"] == 35.0


def test_reverse_breakeven_cpc_scenarios_and_benchmark_zones():
    # CPA 35 (non-IT): 1% -> 0.35 (below_iqr), 2% -> 0.70 (below_iqr), 3% -> 1.05 (below_median)
    low = precheck.analyze(price=60, product_cost=25, market="DE")
    assert low["cpc_scenarios"] == [
        {"cvr_pct": 1, "max_cpc": 0.35, "zone": "below_iqr"},
        {"cvr_pct": 2, "max_cpc": 0.70, "zone": "below_iqr"},
        {"cvr_pct": 3, "max_cpc": 1.05, "zone": "below_median"},
    ]
    # CPA 50: 2% -> 1.00 (below_median), 3% -> 1.50 (above_iqr)
    mid = precheck.analyze(price=80, product_cost=30, market="DE")
    assert mid["cpc_scenarios"][1] == {"cvr_pct": 2, "max_cpc": 1.00, "zone": "below_median"}
    assert mid["cpc_scenarios"][2] == {"cvr_pct": 3, "max_cpc": 1.50, "zone": "above_iqr"}
    # CPA 60: 2% -> 1.20 (within_iqr)
    high = precheck.analyze(price=100, product_cost=40, market="DE")
    assert high["cpc_scenarios"][1] == {"cvr_pct": 2, "max_cpc": 1.20, "zone": "within_iqr"}


def test_poisson_stop_odds_and_max_loss_cap():
    out = precheck.analyze(price=60, product_cost=25, market="IT", test_budget=300)
    stop = out["stop_rule"]
    assert stop["p_zero_2x"] == round(math.exp(-2), 4) == 0.1353
    assert stop["p_zero_per_ad"] == round(math.exp(-2.5), 4) == 0.0821
    assert stop["p_zero_3x"] == round(math.exp(-3), 4) == 0.0498
    assert out["risk"]["round_spend"] == 300.0
    assert out["risk"]["max_loss_billed"] == 309.0

    # At non-IT CPA 35 and spend 300: e^(-300/35) ~= 0.000189 (~1 in 5,281)
    non_it = precheck.analyze(price=60, product_cost=25, market="DE", test_budget=300)
    assert non_it["risk"]["p_zero_round"] == round(math.exp(-300 / 35), 6)
    assert 5200 <= non_it["risk"]["one_in_round"] <= 5350


def test_analyze_rejects_invalid_and_negative_margin_inputs():
    with pytest.raises(ValueError):
        precheck.analyze(price=0, product_cost=10)
    with pytest.raises(ValueError):
        precheck.analyze(price=50, product_cost=30, vat_pct=100)
    with pytest.raises(ValueError):
        precheck.analyze(price=50, product_cost=30, shipping_cost=25)
    with pytest.raises(ValueError):
        precheck.analyze(price=50, product_cost=10, test_budget=-10)


def test_project_clean_preserves_backwards_compatibility_and_validates_optional_costs(tmp_path):
    plain, errors = project.clean(BASE_CARD)
    assert errors == {} and set(plain) == set(project.FIELDS)

    rich, errors = project.clean({
        **BASE_CARD,
        "market": "IT",
        "vat_pct": "22",
        "shipping_cost": "5,5",
        "payment_fee_pct": "2.9",
        "return_rate_pct": "5",
        "ad_fee_pct": "0",
    })
    assert errors == {}
    assert rich["vat_pct"] == 22.0 and rich["shipping_cost"] == 5.5 and rich["ad_fee_pct"] == 0.0

    _, bad = project.clean({**BASE_CARD, "vat_pct": "100", "shipping_cost": "-2", "return_rate_pct": "abc"})
    assert bad == {"vat_pct": "below_100", "shipping_cost": "positive", "return_rate_pct": "number"}

    _, wipeout = project.clean({**BASE_CARD, "shipping_cost": "250"})
    assert wipeout == {"product_cost": "above_price"}


def test_briefs_project_section_and_plan_include_precheck_and_skeptical_jury():
    # briefs.test_numbers stays unchanged for existing callers
    assert "precheck" not in briefs.test_numbers(BASE_CARD)

    it_card = {**BASE_CARD, "price": 122.0, "product_cost": 40.0, "market": "IT", "shipping_cost": 5.0}
    md_it = briefs.project_section(it_card, "it")
    assert "## Prova prima di spendere" in md_it
    assert "maggiorazione Meta +3%" in md_it
    assert "1,06" in md_it and "0,82" in md_it and "1,28" in md_it
    assert "quasi impossibile per sfortuna" in md_it

    md_en = briefs.project_section(BASE_CARD, "en")
    assert "## Test before spending" in md_en
    assert "VAT, shipping, payment fees and returns are set to 0" in md_en
    assert "1.06" in md_en and "nearly impossible by luck alone" in md_en

    plan_it = briefs.instructions("plan", "Competitor", "it")
    plan_en = briefs.instructions("plan", "Competitor", "en")
    assert "giuria scettica di quattro profili" in plan_it and "Nessun complimento" in plan_it
    assert "skeptical jury of four buyer profiles" in plan_en and "zero compliments" in plan_en
