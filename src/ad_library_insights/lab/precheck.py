"""Precheck ("Prova prima di spendere"): reverse-breakeven math & test risk cap.

Pure arithmetic using Python stdlib only. Instead of predicting future ad sales
from Meta's auction, computes from the user's real unit economics:

* effective contribution margin after VAT, shipping, payment fees, returns and
  market-specific Meta ad fees (e.g. +3% in Italy);
* reverse-breakeven max CPC at 1%, 2% and 3% conversion rate, juxtaposed with a
  dated European e-commerce link-click benchmark (median €1.06, IQR €0.82-€1.28,
  as of September 2026);
* explicit first-round maximum loss and settled-ad Poisson zero-sales odds at
  the 2x and 3x CPA cut rules.
"""
from __future__ import annotations

import math

META_AD_FEE_BY_MARKET = {"IT": 3.0}
CVR_SCENARIOS = (0.01, 0.02, 0.03)
EU_CPC_BENCHMARK = {
    "median": 1.06,
    "p25": 0.82,
    "p75": 1.28,
    "currency": "EUR",
    "as_of": "2026-09",
}
DEFAULT_IDEAS = 5
DEFAULT_MULTIPLIER = 2.5


def meta_ad_fee_pct(market: str | None, override: float | None = None) -> float:
    """Market Meta regulatory/ad-spend fee percentage, or an explicit override."""
    if override is not None:
        fee = float(override)
        if not math.isfinite(fee) or fee < 0 or fee >= 100:
            raise ValueError("ad_fee_pct must be between 0 and 100")
        return fee
    return META_AD_FEE_BY_MARKET.get((market or "").strip().upper(), 0.0)


def poisson_zero_prob(spend: float, breakeven_cpa: float) -> float:
    """Probability of zero purchases for a settled ad at ``CPA == breakeven_cpa``."""
    if spend < 0 or not math.isfinite(spend):
        raise ValueError("spend must be non-negative")
    if breakeven_cpa <= 0 or not math.isfinite(breakeven_cpa):
        raise ValueError("breakeven_cpa must be positive")
    return math.exp(-spend / breakeven_cpa)


def _cpc_zone(cpc: float) -> str:
    if cpc < EU_CPC_BENCHMARK["p25"]:
        return "below_iqr"
    if cpc < EU_CPC_BENCHMARK["median"]:
        return "below_median"
    if cpc <= EU_CPC_BENCHMARK["p75"]:
        return "within_iqr"
    return "above_iqr"


def analyze(
    *,
    price: float,
    product_cost: float = 0.0,
    market: str = "",
    vat_pct: float = 0.0,
    shipping_cost: float = 0.0,
    payment_fee_pct: float = 0.0,
    payment_fee_fixed: float = 0.0,
    return_rate_pct: float = 0.0,
    other_costs: float = 0.0,
    ad_fee_pct: float | None = None,
    ideas: int = DEFAULT_IDEAS,
    multiplier: float = DEFAULT_MULTIPLIER,
    test_budget: float | None = None,
) -> dict:
    """Compute real contribution margin, Meta-fee-adjusted CPA, max CPC and Poisson stop odds."""
    price = float(price)
    product_cost = float(product_cost)
    vat_pct = float(vat_pct)
    shipping_cost = float(shipping_cost)
    payment_fee_pct = float(payment_fee_pct)
    payment_fee_fixed = float(payment_fee_fixed)
    return_rate_pct = float(return_rate_pct)
    other_costs = float(other_costs)
    ideas = int(ideas)
    multiplier = float(multiplier)

    if not math.isfinite(price) or price <= 0:
        raise ValueError("price must be greater than zero")
    for name, val in (
        ("product_cost", product_cost),
        ("shipping_cost", shipping_cost),
        ("payment_fee_fixed", payment_fee_fixed),
        ("other_costs", other_costs),
    ):
        if not math.isfinite(val) or val < 0:
            raise ValueError(f"{name} cannot be negative")
    for name, val in (
        ("vat_pct", vat_pct),
        ("payment_fee_pct", payment_fee_pct),
        ("return_rate_pct", return_rate_pct),
    ):
        if not math.isfinite(val) or val < 0 or val >= 100:
            raise ValueError(f"{name} must be at least 0 and below 100")
    if ideas < 1:
        raise ValueError("ideas must be at least 1")
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("multiplier must be greater than zero")
    if test_budget is not None:
        test_budget = float(test_budget)
        if not math.isfinite(test_budget) or test_budget <= 0:
            raise ValueError("test_budget must be greater than zero")

    net_price_raw = price / (1.0 + vat_pct / 100.0)
    payment_fee_raw = price * (payment_fee_pct / 100.0) + payment_fee_fixed
    keep_share = 1.0 - return_rate_pct / 100.0
    net_margin_raw = (net_price_raw - product_cost) * keep_share - shipping_cost - payment_fee_raw - other_costs
    if net_margin_raw <= 0:
        raise ValueError("costs leave no positive margin")

    fee_pct = meta_ad_fee_pct(market, ad_fee_pct)
    cpa_ads_raw = net_margin_raw / (1.0 + fee_pct / 100.0)
    roas_breakeven = net_price_raw / cpa_ads_raw
    has_real_costs = any(
        val > 0
        for val in (vat_pct, shipping_cost, payment_fee_pct, payment_fee_fixed, return_rate_pct, other_costs)
    )

    cpc_scenarios = []
    for cvr in CVR_SCENARIOS:
        max_cpc = round(cpa_ads_raw * cvr, 2)
        cpc_scenarios.append({"cvr_pct": round(cvr * 100), "max_cpc": max_cpc, "zone": _cpc_zone(max_cpc)})

    cut_low = round(cpa_ads_raw * 2.0, 2)
    per_ad = round(cpa_ads_raw * multiplier, 2)
    cut_high = round(cpa_ads_raw * 3.0, 2)
    p_zero_2x = round(poisson_zero_prob(cpa_ads_raw * 2.0, cpa_ads_raw), 4)
    p_zero_per_ad = round(poisson_zero_prob(cpa_ads_raw * multiplier, cpa_ads_raw), 4)
    p_zero_3x = round(poisson_zero_prob(cpa_ads_raw * 3.0, cpa_ads_raw), 4)

    round_spend_raw = test_budget if test_budget is not None else (per_ad * ideas)
    round_spend = round(round_spend_raw, 2)
    max_loss_billed = round(round_spend_raw * (1.0 + fee_pct / 100.0), 2)
    round_p_zero = poisson_zero_prob(round_spend_raw, cpa_ads_raw)
    one_in_round = int(round(1.0 / round_p_zero)) if round_p_zero > 1e-12 else None

    return {
        "inputs": {
            "price": price,
            "product_cost": product_cost,
            "market": (market or "").strip().upper(),
            "vat_pct": vat_pct,
            "shipping_cost": shipping_cost,
            "payment_fee_pct": payment_fee_pct,
            "payment_fee_fixed": payment_fee_fixed,
            "return_rate_pct": return_rate_pct,
            "other_costs": other_costs,
        },
        "net_price": round(net_price_raw, 2),
        "net_margin": round(net_margin_raw, 2),
        "ad_fee_pct": round(fee_pct, 2),
        "cpa_ads": round(cpa_ads_raw, 2),
        "roas_breakeven": round(roas_breakeven, 2),
        "has_real_costs": has_real_costs,
        "benchmark": dict(EU_CPC_BENCHMARK),
        "cpc_scenarios": cpc_scenarios,
        "stop_rule": {
            "cut_low": cut_low,
            "per_ad": per_ad,
            "cut_high": cut_high,
            "p_zero_2x": p_zero_2x,
            "p_zero_per_ad": p_zero_per_ad,
            "p_zero_3x": p_zero_3x,
        },
        "risk": {
            "ideas": ideas,
            "multiplier": multiplier,
            "round_spend": round_spend,
            "max_loss_billed": max_loss_billed,
            "p_zero_round": round(round_p_zero, 6),
            "one_in_round": one_in_round,
            "settled_caveat": True,
        },
    }


def _fmt(value: float | int, lang: str) -> str:
    if isinstance(value, float):
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    else:
        text = f"{int(value):,}"
    return text.translate(str.maketrans(",.", ".,")) if lang == "it" else text


def format_markdown(report: dict, lang: str = "en") -> list[str]:
    """Bilingual Markdown bullets for ``project.md`` and the Level 3 brief."""
    lang = "it" if lang == "it" else "en"
    market = report["inputs"].get("market") or "—"
    fee_pct = report["ad_fee_pct"]
    c1, c2, c3 = report["cpc_scenarios"]
    stop = report["stop_rule"]
    risk = report["risk"]
    bench = report["benchmark"]

    zone_labels = {
        "en": {
            "below_iqr": "below the central market band (€0.82–€1.28) — hard to reach",
            "below_median": "below market median (€1.06) — achievable but demanding",
            "within_iqr": "inside the central market band (€0.82–€1.28)",
            "above_iqr": "above the central market band (€0.82–€1.28) — comfortable headroom",
        },
        "it": {
            "below_iqr": "sotto la fascia centrale del mercato (0,82–1,28 €) — difficile da ottenere",
            "below_median": "sotto la mediana di mercato (1,06 €) — possibile ma impegnativo",
            "within_iqr": "dentro la fascia centrale del mercato (0,82–1,28 €)",
            "above_iqr": "sopra la fascia centrale del mercato (0,82–1,28 €) — buon margine di manovra",
        },
    }[lang]

    one_in = _fmt(risk["one_in_round"], lang) if risk.get("one_in_round") else ("<0.0001%" if lang == "en" else "<0,0001%")

    if lang == "it":
        fee_note = (
            f"; maggiorazione Meta +{fee_pct:g}% su {market}: CPA massimo su Gestione Inserzioni {_fmt(report['cpa_ads'], lang)}"
            if fee_pct > 0
            else ""
        )
        lines = [f"- Margine netto reale per ordine: {_fmt(report['net_margin'], lang)}{fee_note}."]
        if not report["has_real_costs"]:
            lines.append(
                "- Attenzione: IVA, spedizione, commissioni di pagamento e resi sono impostati a 0. "
                "Inserisci i costi reali per evitare un margine gonfiato."
            )
        lines += [
            f"- CPC massimo necessario per andare in pari: a 1% conv. <= {_fmt(c1['max_cpc'], lang)}, "
            f"a 2% conv. <= {_fmt(c2['max_cpc'], lang)} ({zone_labels[c2['zone']]}), "
            f"a 3% conv. <= {_fmt(c3['max_cpc'], lang)}.",
            f"- Benchmark e-commerce UE (settembre 2026): mediana {_fmt(bench['median'], lang)} EUR per clic sul link, "
            f"metà centrale dei brand tra {_fmt(bench['p25'], lang)} e {_fmt(bench['p75'], lang)} EUR.",
            f"- Perdita massima del primo giro ({risk['ideas']} annunci): fino a {_fmt(risk['round_spend'], lang)} "
            + (
                f"su Gestione Inserzioni ({_fmt(risk['max_loss_billed'], lang)} fatturati con +{fee_pct:g}% Meta)."
                if fee_pct > 0
                else "in budget di test."
            ),
            f"- Regola di stop (annuncio già assestato al CPA di pareggio): a 2x ({_fmt(stop['cut_low'], lang)}) 0 vendite "
            f"ha probabilità ~{round(stop['p_zero_2x'] * 100, 1)}%; a 3x ({_fmt(stop['cut_high'], lang)}) scende al "
            f"~{round(stop['p_zero_3x'] * 100, 1)}%; sull'intero giro con 0 vendite è quasi impossibile per sfortuna "
            f"(circa 1 caso su {one_in}, al netto della fase iniziale di apprendimento Meta).",
        ]
        return lines

    fee_note = (
        f"; Meta +{fee_pct:g}% ad fee on {market}: max Ads Manager CPA {_fmt(report['cpa_ads'], lang)}"
        if fee_pct > 0
        else ""
    )
    lines = [f"- Effective net margin per order: {_fmt(report['net_margin'], lang)}{fee_note}."]
    if not report["has_real_costs"]:
        lines.append(
            "- Warning: VAT, shipping, payment fees and returns are set to 0. "
            "Enter your real costs to avoid an inflated break-even."
        )
    lines += [
        f"- Reverse breakeven max CPC: at 1% CVR <= {_fmt(c1['max_cpc'], lang)}, "
        f"at 2% CVR <= {_fmt(c2['max_cpc'], lang)} ({zone_labels[c2['zone']]}), "
        f"at 3% CVR <= {_fmt(c3['max_cpc'], lang)}.",
        f"- EU e-commerce benchmark (September 2026): median EUR {_fmt(bench['median'], lang)} per link click, "
        f"central half of brands between EUR {_fmt(bench['p25'], lang)} and EUR {_fmt(bench['p75'], lang)}.",
        f"- Maximum first-round loss ({risk['ideas']} ads): up to {_fmt(risk['round_spend'], lang)} in Ads Manager"
        + (
            f" ({_fmt(risk['max_loss_billed'], lang)} billed including +{fee_pct:g}% Meta fee)."
            if fee_pct > 0
            else "."
        ),
        f"- Stop rule (settled ad at break-even CPA): at 2x ({_fmt(stop['cut_low'], lang)}) 0 sales "
        f"is ~{round(stop['p_zero_2x'] * 100, 1)}%; at 3x ({_fmt(stop['cut_high'], lang)}) it drops to "
        f"~{round(stop['p_zero_3x'] * 100, 1)}%; zero signal over the full round is nearly impossible by luck alone "
        f"(about 1 in {one_in}, once past Meta's initial learning days).",
    ]
    return lines
