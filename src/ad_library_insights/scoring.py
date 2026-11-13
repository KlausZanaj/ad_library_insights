"""Longevity score: how long an ad has run and how often its copy is reused.

The Ad Library publishes no spend or results for commercial ads. What it does show
is persistence: advertisers rarely keep paying for an ad, or keep cloning its copy
across creatives, unless it earns its place. The score blends both signals:

    age        = min(days_running / horizon_days, 1)
    repetition = min(log(repetitions) / log(repetition_cap), 1)
    score      = 100 * (weight_days * age + weight_repetition * repetition)

``repetitions`` counts every ad carrying the same copy from the same advertiser:
the "N ads use this creative and text" counter of each card, summed over all cards
in the result set whose normalised body text is identical.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from datetime import date


def text_fingerprint(body: str) -> str:
    """Stable id for a piece of copy, ignoring case, punctuation, emoji and spacing."""
    normalised = re.sub(r"[\W_]+", " ", (body or "").casefold()).strip()
    return hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:12] if normalised else ""


def days_running(ad: dict, as_of: date) -> int | None:
    """Days between the start date and the end date (or ``as_of`` if still active)."""
    if not ad.get("started"):
        return None
    end = date.fromisoformat(ad["ended"]) if ad.get("ended") else as_of
    return max(0, (end - date.fromisoformat(ad["started"])).days)


def longevity_score(days: int | None, repetitions: int, horizon_days: int = 90,
                    repetition_cap: int = 10, weight_days: float = 0.6,
                    weight_repetition: float = 0.4) -> float:
    age = min((days or 0) / horizon_days, 1.0)
    repetition = min(math.log(max(repetitions, 1)) / math.log(repetition_cap), 1.0)
    total = weight_days + weight_repetition
    return round(100 * (weight_days * age + weight_repetition * repetition) / total, 1)


def rank_ads(ads: list[dict], as_of: date | None = None, collapse_duplicates: bool = True,
             **weights) -> list[dict]:
    """Return scored copies of ``ads``, best first.

    Each ad gains ``days_running``, ``repetitions``, ``creative_variants`` and
    ``longevity_score``. With ``collapse_duplicates`` the cards sharing one copy are
    merged into their oldest member, which lists the others in ``variant_ids``.
    Ties are broken by the earlier start date.
    """
    as_of = as_of or date.today()
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for ad in ads:
        fingerprint = text_fingerprint(ad.get("body", ""))
        key = ((ad.get("advertiser") or "").casefold(), fingerprint) if fingerprint \
            else ("", ad["library_id"])
        groups[key].append(ad)

    ranked = []
    for members in groups.values():
        members = sorted(members, key=lambda a: (a.get("started") or "9999", a["library_id"]))
        repetitions = sum(a.get("copies", 1) for a in members)
        for index, ad in enumerate(members):
            if collapse_duplicates and index:
                break
            days = days_running(ad, as_of)
            scored = dict(ad, days_running=days, repetitions=repetitions,
                          creative_variants=len(members),
                          longevity_score=longevity_score(days, repetitions, **weights))
            if collapse_duplicates:
                scored["variant_ids"] = [a["library_id"] for a in members[1:]]
            ranked.append(scored)

    ranked.sort(key=lambda a: (-a["longevity_score"], a.get("started") or "9999", a["library_id"]))
    return ranked
