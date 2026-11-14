"""Two advertisers side by side, on the same numbers.

Plain code: it lines up the signals already computed for each company and points out
where they differ enough to matter. It names no winner. More active ads or a faster
launch pace is a difference in how two companies advertise, not a verdict on which
one earns more, which the Ad Library does not show.
"""
from __future__ import annotations

RATIO_WORTH_NOTING = 1.5          # one side at least one and a half times the other
SHARE_GAP_WORTH_NOTING = 0.2      # twenty points of difference in a share


def _name(result: dict) -> str:
    return (result.get("page") or {}).get("name") or result.get("query") or "?"


def _shares(rows: list[dict], key: str, limit: int = 3) -> list[dict]:
    return [{"label": row[key], "share": row["share"]} for row in rows[:limit] if row["share"] >= 0.005]


def profile(result: dict) -> dict:
    """The comparable facts of one company, flat."""
    found = result["signals"]
    ads = result.get("ads") or []
    reach, audience = found["reach"], found.get("audience") or {}
    days = [ad["days_running"] for ad in ads if ad.get("days_running") is not None]
    ages = audience.get("age_ranges") or []
    return {
        "active_ads": found["active_ads"],
        "distinct_texts": found["distinct_texts"],
        "new_per_week": found["new_per_week"],
        "started_last_30_days": found["started_last_30_days"],
        "share_started_last_30_days": found["share_started_last_30_days"],
        "scaling_ads": found["verdicts"].get("scaling", 0),
        "holding_ads": found["verdicts"].get("holding", 0),
        "longest_running_days": max(days) if days else None,
        "most_creatives": max((ad.get("creatives", 1) for ad in ads), default=None),
        "needs_review": found["needs_review"],
        "video_share": found["video_share"],
        "formats": [{"label": name, "share": share} for name, share in list(found["format_share"].items())[:3]],
        "languages": _shares(found["languages"], "language"),
        "share_with_proof": found["copy_patterns"]["share_with_proof"],
        "share_mentioning_offer": found["copy_patterns"]["share_mentioning_offer"],
        "median_reach_per_day": reach.get("median_reach_per_day") if reach.get("available") else None,
        "eu_reach_summed": reach.get("eu_reach_summed") if reach.get("available") else None,
        "country_reach_summed": reach.get("country_reach_summed") if reach.get("available") else None,
        "ads_with_reach": reach.get("ads_with_reach", 0) if reach.get("available") else 0,
        "age_range": f"{ages[0]['age_min']}-{ages[0]['age_max']}" if ages else None,
        "genders": list(audience.get("genders") or {}),
        "breadth": list(audience.get("breadth") or {}),
        "locations_included": (audience.get("locations_included") or [])[:6],
        "locations_excluded": (audience.get("locations_excluded") or [])[:6],
        "locations_count": audience.get("locations_included_count",
                                        len(audience.get("locations_included") or [])),
        "platforms": _shares(found["platforms"], "platform", 5),
        "buttons": _shares(found["buttons"], "button"),
        "destinations": _shares(found["destinations"], "domain"),
    }


# (group, key, kind): the order of the table
ROWS = (
    ("pace", "active_ads", "number"), ("pace", "new_per_week", "number"),
    ("pace", "started_last_30_days", "number"), ("pace", "share_started_last_30_days", "percent"),
    ("pace", "scaling_ads", "number"), ("pace", "holding_ads", "number"),
    ("pace", "longest_running_days", "number"),
    ("pace", "needs_review", "number"),
    ("creative", "video_share", "percent"), ("creative", "formats", "shares"),
    ("creative", "distinct_texts", "number"), ("creative", "most_creatives", "number"),
    ("creative", "share_with_proof", "percent"), ("creative", "share_mentioning_offer", "percent"),
    ("creative", "languages", "languages"),
    ("reach", "median_reach_per_day", "number"), ("reach", "eu_reach_summed", "number"),
    ("reach", "country_reach_summed", "number"), ("reach", "ads_with_reach", "number"),
    ("reach", "age_range", "text"), ("reach", "genders", "genders"), ("reach", "breadth", "breadths"),
    ("reach", "locations_count", "number"), ("reach", "locations_included", "places"),
    ("reach", "locations_excluded", "places"),
    ("route", "platforms", "platforms"), ("route", "buttons", "shares"), ("route", "destinations", "shares"),
)


def _highlights(a: dict, b: dict) -> list[dict]:
    """Differences large enough to say out loud, each with the side that leads."""
    notes = []
    for key in ("active_ads", "new_per_week", "median_reach_per_day"):
        first, second = a.get(key), b.get(key)
        if not first or not second:
            continue
        ratio = max(first, second) / min(first, second)
        if ratio >= RATIO_WORTH_NOTING:
            leader = "a" if first > second else "b"
            notes.append({"key": key, "leader": leader, "ratio": round(ratio, 1),
                          "lead": max(first, second), "trail": min(first, second)})
    if abs(a["video_share"] - b["video_share"]) >= SHARE_GAP_WORTH_NOTING:
        leader = "a" if a["video_share"] > b["video_share"] else "b"
        notes.append({"key": "video_share", "leader": leader,
                      "lead": max(a["video_share"], b["video_share"]),
                      "trail": min(a["video_share"], b["video_share"])})
    for key in ("scaling_ads", "holding_ads"):
        if a[key] != b[key]:
            leader = "a" if a[key] > b[key] else "b"
            notes.append({"key": key, "leader": leader, "lead": max(a[key], b[key]), "trail": min(a[key], b[key])})
    return notes


def compare(first: dict, second: dict) -> dict:
    """Line up two company results: names, a table of rows, and the notable differences."""
    a, b = profile(first), profile(second)
    return {
        "names": {"a": _name(first), "b": _name(second)},
        "country": first.get("country"),
        "rows": [{"group": group, "key": key, "kind": kind, "a": a[key], "b": b[key]}
                 for group, key, kind in ROWS],
        "highlights": _highlights(a, b),
        "note": "Differences in how two companies advertise. The Ad Library shows no spend and no "
                "sales, so this says nothing about which one earns more.",
    }
