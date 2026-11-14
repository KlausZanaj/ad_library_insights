"""Signals computed from the ads, by plain code: no model, no network.

They feed the rating and describe a search as a whole:

* per ad: reach per day and how broad the audience is (the rating itself is in ``rating``);
* per search or advertiser: format mix, launch pace, languages, buttons, destinations,
  repeated copy patterns, and reach and audience summaries where Meta publishes them.

"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from importlib import resources

from . import copy_analysis, rating

AGE_FLOOR, AGE_CEILING = 18, 65      # the age range Meta's targeting spans
_WORD = re.compile(r"[^\W\d_]+")


def _stopwords() -> dict[str, frozenset]:
    raw = json.loads(resources.files(__package__).joinpath("data/stopwords.json").read_text("utf-8"))
    return {code: frozenset(words) for code, words in raw.items() if not code.startswith("_")}


_STOPWORDS = _stopwords()


# writing systems that identify a language (or a small family) on their own
_SCRIPTS = (("ko", re.compile("[가-힯]")), ("ja", re.compile("[぀-ヿ]")),
            ("zh", re.compile("[一-鿿]")), ("ru", re.compile("[Ѐ-ӿ]")),
            ("ar", re.compile("[؀-ۿ]")), ("he", re.compile("[֐-׿]")),
            ("el", re.compile("[Ͱ-Ͽ]")), ("th", re.compile("[฀-๿]")),
            ("hi", re.compile("[ऀ-ॿ]")))


def detect_language(text: str) -> str | None:
    """Best guess of the language of ``text``, or None when it cannot be told.

    Non-Latin scripts are recognised by their characters; Latin-script languages by
    their most common function words, which needs a sentence or two to work.
    """
    text = text or ""
    letters = len(_WORD.findall(text))
    for code, pattern in _SCRIPTS:
        if len(pattern.findall(text)) >= max(3, letters // 2):
            return code
    counts = Counter(_WORD.findall(text.casefold()))
    scores = {code: sum(counts[w] for w in words) for code, words in _STOPWORDS.items()}
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    best, runner_up = ranked[0][1], ranked[1][1]
    if best == 0 or best == runner_up:
        return None
    if best == 1 and (runner_up or sum(counts.values()) > 12):
        return None                       # one common word settles it only in a short text
    return ranked[0][0]


def _share(count: int, total: int) -> float:
    return round(count / total, 2) if total else 0.0


def _table(counter: Counter, total: int, key: str, limit: int = 8) -> list[dict]:
    return [{key: name, "ads": count, "share": _share(count, total)}
            for name, count in counter.most_common(limit)]


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


# --- per ad -----------------------------------------------------------------------

def audience_breadth(audience: dict | None, reach: dict | None) -> dict | None:
    """How wide the targeting is, from age span, gender and locations.

    Each of the three counts up to one point: the full 18-65 span, all genders, and
    a whole country or more. 2.5 points and above reads as broad, 1.5 as medium.
    """
    if not audience:
        return None
    low = audience.get("age_min") or AGE_FLOOR
    high = audience.get("age_max") or AGE_CEILING
    span = max(0, high - low)
    included = audience.get("locations_included") or []
    kinds = {place.get("type") for place in included}
    countries_reached = (reach or {}).get("countries_reached") or 0
    if "country_groups" in kinds or len(included) >= 5 or countries_reached >= 5:
        place_points = 1.0
    elif "countries" in kinds:
        place_points = 0.5
    else:
        place_points = 0.0
    all_genders = (audience.get("gender") or "All").lower() == "all"
    points = min(span / (AGE_CEILING - AGE_FLOOR), 1.0) + (1.0 if all_genders else 0.0) + place_points
    return {
        "age_span_years": span,
        "all_genders": all_genders,
        "locations_included": len(included),
        "locations_excluded": len(audience.get("locations_excluded") or []),
        "countries_reached": countries_reached,
        "label": "broad" if points >= 2.5 else "medium" if points >= 1.5 else "narrow",
    }


def annotate(ranked: list[dict], use_impressions: bool = True) -> list[dict]:
    """Add reach per day and audience breadth to the ads, then rate and sort them.

    Reach per day divides the reach of the ad that was opened by that ad's own days;
    the age of the whole concept (its oldest ad) is what staying power looks at.
    """
    for ad in ranked:
        reach = ad.get("reach") or {}
        days = max(ad.get("ad_days") or ad.get("days_running") or 0, 1)
        if reach.get("available"):
            # Reach is published for the EU and the UK. It measures scale in the market being
            # researched only when that country is one of those the reach covers.
            ad["reach_in_market"] = reach.get("country_reach") is not None or not reach.get("country")
            ad["reach_per_day"] = round(reach["basis_total"] / days)
            ad["country_reach_per_day"] = (round(reach["country_reach"] / days)
                                           if reach.get("country_reach") is not None else None)
        else:
            ad.pop("reach_per_day", None)
            ad.pop("country_reach_per_day", None)
            ad.pop("reach_in_market", None)
        breadth = audience_breadth(ad.get("audience"), reach)
        if breadth:
            ad["audience_breadth"] = breadth
    return rating.evaluate(ranked, use_impressions)


# --- per search or advertiser -----------------------------------------------------

def _launches(ads: list[dict], as_of: date) -> dict:
    starts = [date.fromisoformat(a["started"]) for a in ads if a.get("started")]
    monday = as_of - timedelta(days=as_of.weekday())
    weeks = []
    for back in range(7, -1, -1):
        week_start = monday - timedelta(weeks=back)
        weeks.append({"week_start": week_start.isoformat(),
                      "ads": sum(week_start <= s < week_start + timedelta(days=7) for s in starts)})
    last_28 = sum((as_of - s).days < 28 for s in starts)
    last_30 = sum((as_of - s).days < 30 for s in starts)
    return {"new_per_week": round(last_28 / 4, 1), "started_last_30_days": last_30,
            "share_started_last_30_days": _share(last_30, len(starts)), "weekly_launches": weeks}


def _copy_patterns(ranked: list[dict]) -> dict:
    with_copy = [ad for ad in ranked if (ad.get("body") or "").strip()]
    summary = copy_analysis.summarize([copy_analysis.analyze_ad(ad) for ad in with_copy])
    openers = Counter(" ".join(_WORD.findall(ad["body"].casefold())[:3]) for ad in with_copy)
    reused = sorted((ad for ad in with_copy if ad.get("creatives", 1) > 1),
                    key=lambda a: -a["creatives"])[:5]
    return {
        "texts_analyzed": len(with_copy),
        "reused_texts": [{"library_id": ad["library_id"], "creatives": ad["creatives"],
                          "ads": ad.get("cards", 1),
                          "opening": ad["body"].strip().splitlines()[0][:140]} for ad in reused],
        "repeated_openers": [{"opener": words, "texts": count}
                             for words, count in openers.most_common(5) if words and count > 1],
        "hook_types": summary["hook_types"],
        "common_structures": summary["common_structures"],
        "share_with_proof": summary["share_with_proof"],
        "share_with_urgency": summary["share_with_urgency"],
        "share_mentioning_offer": summary["share_mentioning_offer"],
        "share_mentioning_price": summary["share_mentioning_price"],
    }


def _reach_summary(ranked: list[dict], country: str | None) -> dict:
    checked = [ad for ad in ranked if "reach" in ad]
    known = [ad for ad in checked if ad["reach"].get("available")]
    if not checked:
        return {"checked_ads": 0, "available": False,
                "note": "Reach has not been read yet: it comes from the detail view of each ad."}
    if not known:
        return {"checked_ads": len(checked), "available": False,
                "note": "None of the ads checked has a reach section. Meta publishes reach only "
                        "for ads delivered in the European Union or the United Kingdom."}
    by_country: Counter = Counter()
    for ad in known:
        for region in ad["reach"]["regions"]:
            for row in region["countries"]:
                by_country[row["country"]] += row["reach"]
    rates = [ad["reach_per_day"] for ad in known if ad.get("reach_per_day") is not None]
    country_reach = [ad["reach"]["country_reach"] for ad in known
                     if ad["reach"].get("country_reach") is not None]
    return {
        "checked_ads": len(checked),
        "available": True,
        "ads_with_reach": len(known),
        "ads_without_reach": len(checked) - len(known),
        # the same person can see several ads, so these sums are not unique people
        "eu_reach_summed": sum(ad["reach"]["eu_total"] or 0 for ad in known),
        "uk_reach_summed": sum(ad["reach"]["uk_total"] or 0 for ad in known),
        "country": (country or "").upper() or None,
        "country_reach_summed": sum(country_reach) if country_reach else None,
        "median_reach_per_day": round(statistics.median(rates)) if rates else None,
        "highest_reach_per_day": max(rates) if rates else None,
        "top_countries": [{"country": code, "reach": people}
                          for code, people in by_country.most_common(10)],
        "note": "Reach is published for the European Union and the United Kingdom only.",
    }


def _audience_summary(ranked: list[dict]) -> dict | None:
    known = [ad for ad in ranked if ad.get("audience")]
    if not known:
        return None
    included, excluded = Counter(), Counter()
    kinds: dict[str, str] = {}
    for ad in known:
        for place in ad["audience"]["locations_included"]:
            included[place["name"]] += 1
            kinds[place["name"]] = place.get("type")
        for place in ad["audience"]["locations_excluded"]:
            excluded[place["name"]] += 1
            kinds[place["name"]] = place.get("type")
    ages = Counter((ad["audience"].get("age_min"), ad["audience"].get("age_max")) for ad in known)

    def places(counter: Counter) -> list[dict]:
        return [{"name": name, "type": kinds.get(name), "ads": count}
                for name, count in counter.most_common(20)]

    return {
        "ads_with_audience": len(known),
        "age_ranges": [{"age_min": low, "age_max": high, "ads": count}
                       for (low, high), count in ages.most_common(5)],
        "genders": dict(Counter((ad["audience"].get("gender") or "All") for ad in known).most_common()),
        "breadth": dict(Counter(ad["audience_breadth"]["label"] for ad in known
                                if ad.get("audience_breadth")).most_common()),
        "locations_included": places(included),
        "locations_excluded": places(excluded),
        "locations_included_count": len(included),      # the lists above stop at twenty
        "locations_excluded_count": len(excluded),
        "note": "Locations are what the advertiser chose to target and can lie outside the "
                "regions for which reach is published.",
    }


def summarize(ads: list[dict], ranked: list[dict], as_of: date | None = None,
              library_total: int | None = None, country: str | None = None) -> dict:
    """Signals for a whole search or advertiser.

    ``ads`` are the cards as listed (one per card); ``ranked`` the scored ads after
    identical texts were merged. Format, launch and button figures count cards.
    """
    as_of = as_of or date.today()
    total = len(ads)
    formats = Counter(ad.get("media_type") or "unknown" for ad in ads)
    languages = Counter(lang for lang in (detect_language(ad.get("body", "")) for ad in ads) if lang)
    platforms = Counter(p for ad in ads for p in ad.get("platforms") or [])
    return {
        "active_ads": library_total if library_total is not None else sum(a.get("copies", 1) for a in ads),
        "ads_loaded": total,
        "distinct_texts": len(ranked),
        "format_share": {name: _share(count, total) for name, count in formats.most_common()},
        "video_share": _share(formats.get("video", 0), total),
        **_launches(ads, as_of),
        "languages": _table(languages, sum(languages.values()), "language"),
        "language_unknown": sum(1 for ad in ads if (ad.get("body") or "").strip()) - sum(languages.values()),
        "buttons": _table(Counter((ad.get("cta") or "").title() for ad in ads if ad.get("cta")),
                          total, "button"),
        "destinations": _table(Counter(ad["landing_domain"] for ad in ads if ad.get("landing_domain")),
                               total, "domain"),
        "platforms": _table(platforms, total, "platform"),
        "verdicts": dict(Counter(ad["verdict"] for ad in ranked).most_common()),
        "reliability": dict(Counter(ad["reliability"] for ad in ranked).most_common()),
        "needs_review": sum(bool(ad.get("needs_review")) for ad in ranked),
        "copy_patterns": _copy_patterns(ranked),
        "reach": _reach_summary(ranked, country),
        "audience": _audience_summary(ranked),
    }


def refresh(summary: dict, ranked: list[dict], country: str | None = None) -> dict:
    """Update the parts of a summary that depend on reach, after detail views were read."""
    summary.update(needs_review=sum(bool(ad.get("needs_review")) for ad in ranked),
                   verdicts=dict(Counter(ad["verdict"] for ad in ranked).most_common()),
                   reliability=dict(Counter(ad["reliability"] for ad in ranked).most_common()),
                   reach=_reach_summary(ranked, country), audience=_audience_summary(ranked))
    return summary
