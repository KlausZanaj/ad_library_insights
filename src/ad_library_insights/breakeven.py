"""Break-even CPA and the "cut it" rule for ads that spend without signal.

Pure arithmetic on numbers the user supplies (unit economics plus an Ads Manager
export). Nothing here reads or changes an ad account.

    break-even CPA = price - product cost - shipping - payment fees - other costs

It is the most you can pay to acquire one order without losing money on it.
An ad that has spent ``multiplier`` times that amount (2-3x is the usual range)
with no add-to-cart and no purchase has had a fair test and should be cut.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# Header fragments seen in Ads Manager exports (English and Italian), lower-case.
COLUMN_ALIASES = {
    "name": ("ad name", "ad set name", "campaign name", "nome dell'inserzione",
             "nome del gruppo di inserzioni", "nome della campagna", "name", "nome"),
    "spend": ("amount spent", "importo speso", "spend", "spesa", "cost"),
    "add_to_cart": ("adds to cart", "add to cart", "aggiunte al carrello", "add_to_cart", "atc"),
    "purchases": ("purchases", "acquisti", "website purchases", "orders", "ordini", "results"),
}


def breakeven_cpa(price: float, product_cost: float = 0.0, shipping_cost: float = 0.0,
                  payment_fee_pct: float = 0.0, payment_fee_fixed: float = 0.0,
                  other_costs: float = 0.0) -> float:
    """Contribution margin per order before ad spend. ``payment_fee_pct`` is a percentage of price."""
    if price <= 0:
        raise ValueError("price must be greater than zero")
    margin = (price - product_cost - shipping_cost - price * payment_fee_pct / 100
              - payment_fee_fixed - other_costs)
    return round(margin, 2)


def judge_ad(spend: float, add_to_cart: float, purchases: float, breakeven: float,
             multiplier: float = 2.5) -> tuple[str, str]:
    """Return (verdict, reason) for one ad. Verdicts: cut, watch, review, keep, wait."""
    if breakeven <= 0:
        raise ValueError("break-even CPA must be positive: the product loses money before ads")
    ratio = spend / breakeven
    if purchases > 0:
        cpa = spend / purchases
        if cpa <= breakeven:
            return "keep", f"CPA {cpa:.2f} is at or below break-even {breakeven:.2f}"
        return "review", f"CPA {cpa:.2f} is above break-even {breakeven:.2f}"
    if ratio >= multiplier:
        if add_to_cart == 0:
            return "cut", (f"spent {ratio:.1f}x break-even CPA with no add to cart and no purchase")
        return "review", f"spent {ratio:.1f}x break-even CPA with add to carts but no purchase"
    if ratio >= 1:
        return "watch", f"spent {ratio:.1f}x break-even CPA, no purchase yet (cut at {multiplier}x)"
    return "wait", f"spent {ratio:.1f}x break-even CPA: not enough data"


def evaluate_ads(rows: list[dict], breakeven: float, multiplier: float = 2.5) -> list[dict]:
    """Judge rows shaped like {"name", "spend", "add_to_cart", "purchases"}; "cut" first."""
    order = {"cut": 0, "review": 1, "watch": 2, "wait": 3, "keep": 4}
    judged = []
    for row in rows:
        spend = float(row.get("spend") or 0)
        atc = float(row.get("add_to_cart") or 0)
        purchases = float(row.get("purchases") or 0)
        verdict, reason = judge_ad(spend, atc, purchases, breakeven, multiplier)
        judged.append({
            "name": row.get("name") or "",
            "spend": spend, "add_to_cart": atc, "purchases": purchases,
            "cpa": round(spend / purchases, 2) if purchases else None,
            "spend_vs_breakeven": round(spend / breakeven, 2),
            "verdict": verdict, "reason": reason,
        })
    judged.sort(key=lambda r: (order[r["verdict"]], -r["spend"]))
    return judged


def _number(value: str) -> float:
    """Parse "1,234.50", "1.234,50", "€ 12" or "" into a float."""
    text = re.sub(r"[^\d.,\-]", "", value or "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def load_ads_csv(path: str | Path) -> list[dict]:
    """Read an Ads Manager CSV export, matching columns by the aliases above."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        headers = reader.fieldnames or []
        mapping = {}
        for field, aliases in COLUMN_ALIASES.items():
            mapping[field] = next((h for alias in aliases for h in headers
                                   if h.strip().casefold().startswith(alias)), None)
        if not mapping["spend"]:
            raise ValueError(f"no spend column found in {headers}")
        return [{
            "name": row.get(mapping["name"], "") if mapping["name"] else "",
            "spend": _number(row.get(mapping["spend"], "")),
            "add_to_cart": _number(row.get(mapping["add_to_cart"], "")) if mapping["add_to_cart"] else 0.0,
            "purchases": _number(row.get(mapping["purchases"], "")) if mapping["purchases"] else 0.0,
        } for row in reader]
