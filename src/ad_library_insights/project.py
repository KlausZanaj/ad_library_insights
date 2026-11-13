"""The user's own project: what they sell, at what price, where, and what hurts.

The Plan level is written for this project, so it is asked once and kept on the
user's machine (``project.json`` in the tool's home folder). Without it no plan is
prepared: one more question beats a generic plan.
"""
from __future__ import annotations

import json
from pathlib import Path

from .storage import home_dir

FIELDS = ("product", "price", "product_cost", "market", "goal", "main_problem")
TEXT_FIELDS = ("product", "goal", "main_problem")


def _path(directory: Path | None = None) -> Path:
    return (Path(directory) if directory else home_dir()) / "project.json"


def _number(value) -> float | None:
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def clean(data: dict) -> tuple[dict, dict]:
    """Normalise a submitted card. Returns ``(card, errors)``; errors map field to a code."""
    data = data or {}
    card, errors = {}, {}
    for field in TEXT_FIELDS:
        card[field] = " ".join(str(data.get(field) or "").split())
        if not card[field]:
            errors[field] = "required"
    for field in ("price", "product_cost"):
        card[field] = _number(data.get(field))
        if card[field] is None:
            errors[field] = "number"
        elif card[field] < 0 or (field == "price" and card[field] == 0):
            errors[field] = "positive"
    if not {"price", "product_cost"} & set(errors) and card["product_cost"] >= card["price"]:
        errors["product_cost"] = "above_price"
    card["market"] = str(data.get("market") or "").strip().upper()
    if not (len(card["market"]) == 2 and card["market"].isalpha()):
        errors["market"] = "country"
    return card, errors


def load(directory: Path | None = None) -> dict | None:
    """The saved card, or None when it is missing or no longer valid."""
    try:
        card, errors = clean(json.loads(_path(directory).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
    return None if errors else card


def save(data: dict, directory: Path | None = None) -> tuple[dict, dict]:
    """Validate and store the card. Nothing is written when there are errors."""
    card, errors = clean(data)
    if not errors:
        path = _path(directory)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    return card, errors
