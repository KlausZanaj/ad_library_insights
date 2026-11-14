"""Rate ads the way a media buyer reads them: scale, staying power, creative investment.

The Ad Library shows no spend and no sales, so no single number is the truth. Three
things can be read from it, and they are kept apart:

* **Scale**: how many people an ad reaches per day in the country that was searched.
  It is the closest thing to spend, because Meta does not show an ad to more people
  without budget. Meta publishes reach for ads delivered in the EU or the UK, country
  by country: the figure of the searched country is the one that rates, the EU total
  is shown beside it. Where the searched country has no such figure, the position in
  the library's own list is used instead, since that list is ordered by total
  impressions, highest first. Reach per day is never divided by fewer than seven
  days: a figure from one or two days says nothing about a rate.
* **Staying power**: days running, full marks at 90 days. Time is not relative: three
  months of spend are three months for a corner shop and for a marketplace.
* **Creative investment**: how many different creatives carry the same concept.
  Identical copies in several ad sets, versions of one dynamic ad, catalogue ads and
  translations of the same ad do not count; they are grouped into one ad with variants.

Scale and creative investment are measured against the other ads of the same search,
on a log scale, because reach runs from hundreds to millions. Every rating carries a
reliability: high when reach was read, medium when only the impression position is
known, low when neither is.

The older longevity score (days and copy reuse) is still computed and shown in the
detail of an ad. It no longer decides the ranking.
"""
from __future__ import annotations

import math
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from . import scoring

HORIZON_DAYS = 90                 # staying power is full from here on
TESTING_DAYS = 30                 # younger than this, an ad is still a test
MIN_RATE_DAYS = 7                 # reach per day is never computed over fewer days than this,
                                  # and an ad younger than this is too recent to judge
WEIGHTS = {                       # points each part can give, by what is known about scale
    "high": {"scale": 60, "staying": 25, "creative": 15},
    "medium": {"scale": 50, "staying": 30, "creative": 20},
    "low": {"scale": 0, "staying": 60, "creative": 40},
}
LOW_SCALE, MID_SCALE, HIGH_SCALE = 25, 40, 70     # positions on the 0-100 scale of the search
MIN_REACH_SAMPLE = 3              # fewer ads with reach than this cannot set a scale


# --- one ad per concept ---------------------------------------------------------------

def media_key(ad: dict) -> str:
    """Identity of the creative: the video file when there is one, else the picture."""
    url = ad.get("video_url") or ad.get("image_url") or ""
    return Path(urlparse(url).path).name or f"ad:{ad['library_id']}"


def skeleton(text: str) -> str:
    """What survives translation: emoji and digits, in order."""
    return "".join(ch for ch in text or "" if unicodedata.category(ch) in ("So", "Nd"))


def _are_translations(first: dict, second: dict) -> bool:
    """Two texts of one advertiser that say the same thing in different languages.

    Evidence, strongest first: the same video or picture under both texts; the same
    emoji and digits in the same order, in two different languages and at a similar
    length. Texts with neither a shared creative nor such marks are left apart.
    """
    if first["language"] and first["language"] == second["language"]:
        return False
    marks_match = bool(first["skeleton"]) and first["skeleton"] == second["skeleton"]
    both_known = bool(first["language"] and second["language"])
    if first["media"] & second["media"]:
        return marks_match or both_known
    one_known = bool(first["language"] or second["language"])     # a short text may go unrecognised
    shorter, longer = sorted((first["words"], second["words"]))
    return marks_match and one_known and shorter >= 0.55 * longer


def _kind(members: list[dict]) -> str:
    """catalog: a product feed fills the ad; dynamic: one ad with several versions."""
    formats = [m.get("format") for m in members]
    if formats.count("dpa") * 2 >= len(members):
        return "catalog"
    links = {m.get("landing_url") for m in members if m.get("landing_url")}
    if len(members) >= 4 and len(links) * 2 >= len(members) and len(links) >= 4:
        return "catalog"                           # same text, a different product behind each ad
    if formats.count("dco") * 2 >= len(members) or sum(bool(m.get("multiple_versions")) for m in members) * 2 >= len(members):
        return "dynamic"
    return "standard"


def group_concepts(ads: list[dict], as_of: date | None = None) -> list[dict]:
    """Merge the cards of a search into one ad per concept.

    Cards of one advertiser sharing a text are one concept; so are translations of that
    text. The concept is represented by its most shown card (best impression position)
    and remembers what it merged: how many cards, identical copies, creatives, languages.
    """
    from .signals import detect_language          # here to avoid a circular import

    as_of = as_of or date.today()
    texts: dict[tuple, dict] = {}
    for ad in ads:
        fingerprint = scoring.text_fingerprint(ad.get("body", ""))
        advertiser = (ad.get("advertiser") or "").casefold()
        key = (advertiser, fingerprint) if fingerprint else ("", ad["library_id"])
        group = texts.setdefault(key, {"advertiser": advertiser, "members": [], "media": set(),
                                       "language": detect_language(ad.get("body", "")),
                                       "skeleton": skeleton(ad.get("body", "")), "text": bool(fingerprint),
                                       "words": max(len((ad.get("body") or "").split()), 1)})
        group["members"].append(ad)
        group["media"].add(media_key(ad))

    # translations: union of text groups within one advertiser
    groups = list(texts.values())
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_advertiser: dict[str, list[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        if group["text"]:
            by_advertiser[group["advertiser"]].append(index)
    for indexes in by_advertiser.values():
        for a, i in enumerate(indexes):
            for j in indexes[a + 1:]:
                if find(i) != find(j) and _are_translations(groups[i], groups[j]):
                    parent[find(j)] = find(i)

    concepts: dict[int, list[dict]] = defaultdict(list)
    for index, group in enumerate(groups):
        concepts[find(index)].append(group)

    ranked = []
    for parts in concepts.values():
        members = [m for part in parts for m in part["members"]]
        lead = min(members, key=lambda m: (m.get("impression_rank") or 10 ** 9, m.get("started") or "9999", m["library_id"]))
        starts = [m["started"] for m in members if m.get("started")]
        first_started = min(starts) if starts else None
        days = scoring.days_running({"started": first_started, "ended": lead.get("ended")}, as_of) if first_started else None
        kind = _kind(members)
        copies = sum(m.get("copies", 1) for m in members)
        creatives = 1 if kind == "catalog" else max(1, len({media_key(m) for m in members}))
        ranks = [m["impression_rank"] for m in members if m.get("impression_rank")]
        ranked.append(dict(
            lead,
            started=first_started or lead.get("started"),
            ad_started=lead.get("started"),
            days_running=days,
            ad_days=scoring.days_running(lead, as_of),
            impression_rank=min(ranks) if ranks else None,
            kind=kind,
            creatives=creatives,
            cards=len(members),
            copies_total=copies,
            texts=len(parts),
            languages=sorted({part["language"] for part in parts if part["language"]}),
            products=len({m.get("headline") for m in members if m.get("headline")}) if kind == "catalog" else None,
            variant_ids=[m["library_id"] for m in members if m is not lead],
            # the earlier longevity calculation, kept as a visible component
            repetitions=copies,
            creative_variants=len(members),
            longevity_score=scoring.longevity_score(days, copies),
            longevity_parts={"days": scoring.longevity_score(days, 1), "reuse": scoring.longevity_score(0, copies)},
        ))
    return evaluate(ranked)


# --- rating ---------------------------------------------------------------------------

def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _log_position(value: float, low: float, high: float) -> float:
    """Where ``value`` sits between ``low`` and ``high`` on a log scale, 0-100."""
    if value <= 0:
        return 0.0
    if high <= low:
        return 100.0
    share = (math.log(max(value, low)) - math.log(low)) / (math.log(high) - math.log(low))
    return round(100 * min(max(share, 0.0), 1.0), 1)


def too_recent(days: int | None) -> bool:
    return days is not None and days < MIN_RATE_DAYS


def _verdict(days: int | None, scale: float | None, reliability: str, leading: bool = True) -> str:
    if too_recent(days):
        return "testing"                           # a few days of delivery cannot be called anything else
    long_running = days is not None and days >= HORIZON_DAYS
    if scale is not None:
        if long_running and scale <= LOW_SCALE:
            return "review"                        # long on air, few people: possibly forgotten
        if scale >= HIGH_SCALE and leading and (reliability == "high" or not long_running):
            return "scaling"
        if long_running and scale >= MID_SCALE:
            return "holding"
    elif long_running:
        return "holding"
    if days is not None and days < TESTING_DAYS:
        return "testing"
    return "average"


def _market_reach(ad: dict) -> float | None:
    """People reached per day in the country being researched; None when that is not known."""
    return ad.get("reach_per_day") if ad.get("reach_in_market", True) else None


def rate_days(ad: dict) -> int:
    """Days the reach of an ad is spread over: its own days on air, seven at the least."""
    own = ad.get("ad_days") if ad.get("ad_days") is not None else ad.get("days_running")
    return max(own or 0, MIN_RATE_DAYS)


def _reach_by_position(ranked: list[dict]):
    """Estimate reach in the searched country from the impression position.

    It uses the ads whose reach in that country is known (the same figure the scale uses).

    The list is ordered by total impressions, so between two ads with known reach an ad
    is given a reach in between (on a log scale); past the last known one it falls off
    in proportion to the position. Returns a function, or None when nothing is known.
    """
    known = sorted((ad["impression_rank"], ad["reach_total"]) for ad in ranked
                   if ad.get("impression_rank") and _market_reach(ad) and ad.get("reach_total"))
    if not known:
        return None

    def estimate(rank: int) -> float:
        before = [point for point in known if point[0] <= rank]
        after = [point for point in known if point[0] >= rank]
        if before and after:
            (r0, t0), (r1, t1) = before[-1], after[0]
            if r0 == r1:
                return float(t0)
            share = (rank - r0) / (r1 - r0)
            return math.exp(math.log(t0) + share * (math.log(t1) - math.log(t0)))
        if after:
            return float(after[0][1])
        r0, t0 = before[-1]
        return t0 * r0 / rank

    return estimate


def evaluate(ranked: list[dict], use_impressions: bool = True) -> list[dict]:
    """Rate every ad against the others in ``ranked`` and sort the list in place, best first.

    Call it again after reach has been read: ads with reach move to a high-reliability
    rating based on people reached per day, and the ads not opened get an estimate from
    their impression position, calibrated on the ones that were. ``use_impressions``
    switches off the impression-position fallback where the list order cannot be trusted.
    """
    reach_rates = [_market_reach(ad) for ad in ranked if _market_reach(ad)]
    reach_scale = len(reach_rates) >= MIN_REACH_SAMPLE
    low_reach = _quantile(reach_rates, 0.05) if reach_scale else 0
    high_reach = max(reach_rates) if reach_scale else 0
    estimate_reach = _reach_by_position(ranked) if reach_scale and use_impressions else None
    by_position = sorted((ad for ad in ranked if ad.get("impression_rank")), key=lambda ad: ad["impression_rank"])
    position = {ad["library_id"]: index for index, ad in enumerate(by_position)}
    most_creatives = max([ad.get("creatives", 1) for ad in ranked] + [3])

    rated = []
    for ad in ranked:
        days = ad.get("days_running")
        staying = round(100 * min((days or 0) / HORIZON_DAYS, 1.0), 1)
        creative = _log_position(ad.get("creatives", 1), 1, most_creatives) if ad.get("creatives", 1) > 1 else 0.0
        ad.pop("reach_per_day_estimate", None)
        if reach_scale and _market_reach(ad) is not None:
            scale, basis, reliability = _log_position(_market_reach(ad), low_reach, high_reach), "reach", "high"
        elif estimate_reach and ad.get("impression_rank"):
            guess = estimate_reach(ad["impression_rank"]) / rate_days(ad)
            ad["reach_per_day_estimate"] = round(guess)
            scale, basis, reliability = _log_position(guess, low_reach, high_reach), "impressions", "medium"
        elif use_impressions and ad["library_id"] in position:
            last = max(len(by_position) - 1, 1)
            scale, basis, reliability = round(100 * (1 - position[ad["library_id"]] / last), 1), "impressions", "medium"
        else:
            scale, basis, reliability = None, None, "low"
        rated.append((ad, scale, basis, reliability, staying, creative))

    # "scaling" is for the ads that lead the search on scale, not for everything above a line
    scales = sorted((scale for _, scale, *_ in rated if scale is not None), reverse=True)
    leading_from = scales[max(1, math.ceil(len(scales) / 3)) - 1] if scales else None

    for ad, scale, basis, reliability, staying, creative in rated:
        days = ad.get("days_running")
        weights = WEIGHTS[reliability]
        points = {"scale": round((scale or 0) * weights["scale"] / 100, 1),
                  "staying": round(staying * weights["staying"] / 100, 1),
                  "creative": round(creative * weights["creative"] / 100, 1)}
        verdict = _verdict(days, scale, reliability, leading=scale is not None and scale >= leading_from)
        if verdict == "review" and "reach_per_day_estimate" in ad:
            verdict = "average"            # an estimate is not enough to call an ad forgotten
        ad.update(
            score=round(sum(points.values()), 1),
            score_parts={"scale": scale, "staying": staying, "creative": creative},
            score_points=points,
            score_weights=dict(weights),
            scale_basis=basis,
            reliability=reliability,
            verdict=verdict,
            needs_review=verdict == "review",
            too_recent=too_recent(days),
        )
        if verdict == "review":
            ad["review"] = {"reason": "long_running_low_scale", "basis": basis}
        else:
            ad.pop("review", None)
    ranked.sort(key=lambda ad: (-ad["score"], -(ad["score_parts"]["scale"] or 0), -(ad.get("days_running") or 0),
                                ad["library_id"]))
    return ranked
