"""Rate ads the way a media buyer reads them: scale, staying power, creative investment.

The Ad Library shows no spend and no sales, so no single number is the truth. Three
things can be read from it, and they are kept apart:

* **Scale**: how many people a concept reaches per day in the country that was
  searched. It is the closest thing to spend, because Meta does not show an ad to more
  people without budget. Meta publishes reach for ads delivered in the EU or the UK,
  country by country: the figure of the searched country is the one that rates, the EU
  total is shown beside it. Reach is divided by the days the ad has been on air, never
  by fewer than 7 (a day or two is not a rate). It is an average over the whole life of
  the ad: reach counts unique people, who grow slower than days, so an ad on air for
  months shows fewer people per day than it had; the total is always shown beside it.
  The ads of one concept that were read are added up. Where the searched country has no such
  figure, the position in the library's own list is used instead, since that list is
  ordered by total impressions, highest first.
* **Staying power**: days running, full marks at 90 days. Time is not relative: three
  months of spend are three months for a corner shop and for a marketplace.
* **Creative investment**: how many different creatives carry the same concept, full
  marks at 10. Identical copies in several ad sets, versions of one dynamic ad,
  catalogue ads and translations of the same ad do not count; they are grouped into
  one ad with variants.

Scale is measured against the best ad of the same search, on a log scale, because
reach runs from hundreds to millions: 100 for the ad that reaches the most people per
day, 0 for one that reaches a thousand times fewer. An ad younger than seven days is
too recent to judge and does not set that yardstick. The three parts always weigh the
same (60, 25, 15). An ad whose reach was not read gets a prudent estimate from its
position in the list: never more than the lowest reach read among the ads listed
before it, and never a scale above the lowest scale among the ads that were read, so
that missing data is not an advantage. Every rating carries a reliability: high when
reach was read, medium when scale rests on the impression position, low when neither
is known. The labels that compare ads with each other ("scaling", "review") are given
only on reach that was read.

The older longevity score (days and copy reuse) is still computed and shown in the
detail of an ad. It no longer decides the ranking.
"""
from __future__ import annotations

import math
import re
import statistics
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
SCALING_MIN_DAYS = 14             # two weeks on air before an ad can be said to scale
WEIGHTS = {"scale": 60, "staying": 25, "creative": 15}     # points each part can give
FULL_CREATIVES = 10               # creative investment is full from here on
SCALE_SPAN = 1000                 # scale 0 is a thousand times fewer people per day than the best ad
LOW_SCALE, MID_SCALE, HIGH_SCALE = 25, 40, 70     # positions on the 0-100 scale of the search
MIN_REACH_SAMPLE = 3              # fewer ads with reach than this cannot set a scale
MIN_COMPARABLE = 5                # fewer than this, no ad is called scaling or forgotten against the others
CARDS_PER_CONCEPT = 3             # ads of one concept whose reach is read and added up
READS_PER_CONCEPT_ASKED = 2       # ceiling of ads opened: this many for every concept asked for
_WORDS = re.compile(r"[^\W_]+")


# --- one ad per concept ---------------------------------------------------------------

def media_key(ad: dict) -> str:
    """Identity of the creative: the video file when there is one, else the picture."""
    url = ad.get("video_url") or ad.get("image_url") or ""
    return Path(urlparse(url).path).name or f"ad:{ad['library_id']}"


def skeleton(text: str) -> str:
    """What survives translation: emoji and digits, in order."""
    return "".join(ch for ch in text or "" if unicodedata.category(ch) in ("So", "Nd"))


def _share_words(first: dict, second: dict) -> bool:
    """Texts in one language share their content words; translations share little more than the brand."""
    shared = first["long_words"] & second["long_words"]
    return len(shared) > 0.25 * max(1, min(len(first["long_words"]), len(second["long_words"])))


def _are_translations(first: dict, second: dict) -> bool:
    """Two texts of one advertiser that say the same thing in different languages.

    Never two texts recognised as the same language, and never two texts that share
    their words. Then one of these: the same video or picture under both, with two
    different languages recognised or the same emoji and digits in the same order; or
    different creatives, with the same emoji and digits at a similar length. A single
    shared mark is weak evidence, so it also asks for two recognised languages.
    """
    known = bool(first["language"] and second["language"])
    if (known and first["language"] == second["language"]) or _share_words(first, second):
        return False
    marks = first["skeleton"] if first["skeleton"] == second["skeleton"] else ""
    if first["media"] & second["media"]:
        return known or bool(marks)
    shorter, longer = sorted((first["words"], second["words"]))
    return bool(marks) and shorter >= 0.55 * longer and (len(marks) >= 2 or known)


def _page_of(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".rstrip("/").casefold()


def _kind(members: list[dict]) -> str:
    """catalog: a product feed fills the ad; dynamic: one ad with several versions."""
    formats = [m.get("format") for m in members]
    if formats.count("dpa") * 2 >= len(members):
        return "catalog"
    # same text, a different product page and a different title behind each ad; tracking
    # parameters after the "?" do not make a different page
    pages = {_page_of(m["landing_url"]) for m in members if m.get("landing_url")}
    titles = {m.get("headline") for m in members if m.get("headline")}
    if len(members) >= 4 and len(pages) >= 4 and len(pages) * 2 >= len(members) and len(titles) * 2 >= len(members):
        return "catalog"
    if formats.count("dco") * 2 >= len(members) or sum(bool(m.get("multiple_versions")) for m in members) * 2 >= len(members):
        return "dynamic"
    return "standard"


def group_concepts(ads: list[dict], as_of: date | None = None) -> list[dict]:
    """Merge the cards of a search into one ad per concept.

    Cards of one advertiser sharing a text are one concept; so are translations of that
    text. The concept is represented by its most shown card (best impression position)
    and remembers what it merged: its cards with their dates and positions, identical
    copies, creatives, languages.
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
                                       "words": max(len((ad.get("body") or "").split()), 1),
                                       "long_words": {word for word in _WORDS.findall((ad.get("body") or "").casefold())
                                                      if len(word) >= 4}})
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
        # a concept is over only when every one of its ads is; then it ended with the last of them
        running = [m for m in members if m.get("status") != "inactive" and not m.get("ended")]
        end_dates = [m["ended"] for m in members if m.get("ended")]
        ended = None if running else (max(end_dates) if end_dates else None)
        days = (None if (not running and ended is None)
                else scoring.days_running({"started": first_started, "ended": ended}, as_of)
                if first_started else None)
        cards = sorted(({"library_id": m["library_id"], "impression_rank": m.get("impression_rank"),
                         "started": m.get("started"), "days": scoring.days_running(m, as_of)} for m in members),
                       key=lambda m: (m["impression_rank"] or 10 ** 9, m["library_id"]))
        ages = [card["days"] for card in cards if card["days"] is not None]
        kind = _kind(members)
        copies = sum(m.get("copies", 1) for m in members)
        creatives = 1 if kind == "catalog" else max(1, len({media_key(m) for m in members}))
        ranks = [m["impression_rank"] for m in members if m.get("impression_rank")]
        ranked.append(dict(
            lead,
            started=first_started or lead.get("started"),
            ended=ended,
            status="inactive" if not running else lead.get("status"),
            ad_started=lead.get("started"),
            days_running=days,
            ad_days=scoring.days_running(lead, as_of),
            newest_days=min(ages) if ages else None,
            impression_rank=min(ranks) if ranks else None,
            kind=kind,
            creatives=creatives,
            cards=len(members),
            members=cards,
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


def read_ceiling(concepts: int) -> int:
    """The most ads opened when ``concepts`` concepts are asked for."""
    return max(0, concepts) * READS_PER_CONCEPT_ASKED


def _by_list_order(ranked: list[dict]) -> list[dict]:
    """Concepts in the order of the library's own list: by their most shown ad."""
    keyed, seen = [], set()
    for place, ad in enumerate(ranked):
        if ad["library_id"] not in seen:             # a concept handed in twice is opened once
            seen.add(ad["library_id"])
            keyed.append((ad.get("impression_rank") or 10 ** 9, place, ad))
    return [ad for _, _, ad in sorted(keyed, key=lambda item: item[:2])]


def _other_cards(ad: dict) -> list[dict]:
    """The second and third most shown ad of a concept: the ones read after its first."""
    return [card for card in ad.get("members") or [] if card["library_id"] != ad["library_id"]][:CARDS_PER_CONCEPT - 1]


def other_cards(ad: dict) -> list[dict]:
    """The second and third most shown ad of a concept."""
    return _other_cards(ad)


def cards_to_read(ranked: list[dict], concepts: int, skip: frozenset | set = frozenset(),
                  ceiling: int | None = None) -> list[tuple[dict, str]]:
    """The ads to open so that the ``concepts`` most shown concepts are read, as (concept, card id).

    Concepts are taken in the order of the library's own list, so the choice does not
    depend on a rating that reach itself will change. First comes the most shown ad of
    each concept: that is what makes a concept "read". Then, while the ceiling allows,
    the second and third ad of those same concepts, the most shown first, so that a
    concept split over many ads is not judged on one of them. A concept gives at most
    ``CARDS_PER_CONCEPT`` ads. ``skip`` holds concepts already tried; ``ceiling`` is
    the most ads opened in all (``read_ceiling`` when not given).
    """
    ceiling = read_ceiling(concepts) if ceiling is None else ceiling
    chosen = first_concepts(ranked, concepts, skip)[:max(0, ceiling)]
    return [(ad, ad["library_id"]) for ad in chosen] + more_cards(chosen, ceiling - len(chosen))


def first_concepts(ranked: list[dict], concepts: int, skip: frozenset | set = frozenset()) -> list[dict]:
    """The ``concepts`` most shown concepts of the library's list, leaving out the ones in ``skip``."""
    return [ad for ad in _by_list_order(ranked) if ad["library_id"] not in skip][:max(0, concepts)]


def more_cards(chosen: list[dict], room: int) -> list[tuple[dict, str]]:
    """Up to ``room`` second and third ads of the concepts in ``chosen``, the most shown first."""
    extras = sorted((card.get("impression_rank") or 10 ** 9, card["library_id"], place)
                    for place, ad in enumerate(chosen) for card in _other_cards(ad))
    return [(chosen[place], card_id) for _, card_id, place in extras[:max(0, room)]]


def cards_left_out(targets: list[tuple[dict, str]]) -> int:
    """Second and third ads of the concepts in ``targets`` that the ceiling kept closed."""
    opened = {card_id for _, card_id in targets}
    concepts = {ad["library_id"]: ad for ad, _ in targets}.values()
    return sum(1 for ad in concepts for card in _other_cards(ad) if card["library_id"] not in opened)


# --- rating ---------------------------------------------------------------------------

def rate_days(days: int | None) -> int:
    """Days a reach figure is spread over: the ad's days on air, seven at the least."""
    return max(days or 0, MIN_RATE_DAYS)


def too_recent(days: int | None) -> bool:
    return days is not None and days < MIN_RATE_DAYS


def _scale_from_rate(rate: float, best: float) -> float:
    """Where ``rate`` sits below ``best`` on a log scale: 100 at the best, 0 a thousand times lower."""
    if rate <= 0 or best <= 0:
        return 0.0
    share = 1 - math.log(best / rate) / math.log(SCALE_SPAN)
    return round(100 * min(max(share, 0.0), 1.0), 1)


def _scale_from_position(rank: int, listed: int) -> float:
    """Where a position sits in a list of ``listed`` ads, on a log scale: 100 for the first.

    The whole library list is the yardstick, not the part that was loaded, so loading
    more or fewer ads does not move the others.
    """
    if listed <= 1:
        return 100.0
    return round(100 * min(max(1 - math.log(max(rank, 1)) / math.log(listed), 0.0), 1.0), 1)


def _market_reach(ad: dict) -> float | None:
    """People reached per day in the country being researched; None when that is not known."""
    return ad.get("reach_per_day") if ad.get("reach_in_market", True) else None


def _reach_by_position(ranked: list[dict]):
    """Estimate reach in the searched country from the impression position.

    It uses the cards whose reach in that country was read (the same figures the scale
    uses). The list is ordered by total impressions, in every country together, so a
    position says little about one country: an ad between two that reach many people
    there can reach almost nobody. The estimate is therefore the prudent one: the lowest
    reach read among the cards listed before it; past the last card read it falls off in
    proportion to the position. Returns a function, or None when nothing is known.
    """
    known = sorted((rank, total) for ad in ranked for rank, total in ad.get("reach_points") or []
                   if rank and total >= 0)
    if not known:
        return None

    def estimate(rank: int) -> float:
        before = [point for point in known if point[0] <= rank]
        after = [point for point in known if point[0] >= rank]
        if not before:
            return float(after[0][1])
        lowest = float(min(total for _, total in before))
        return lowest if after else lowest * before[-1][0] / rank

    return estimate


def _verdict(ad: dict, scale: float | None, read: bool, comparable: bool, leading: bool, small: bool) -> str:
    """The label of an ad.

    ``read``: its reach was read; ``comparable``: enough ads were read to compare them;
    ``leading``: in the top third by scale; ``small``: total reach below the middle of the search.
    """
    days = ad.get("days_running")
    if ad.get("status") == "inactive":
        return "ended"
    if too_recent(days):
        return "testing"                           # a few days of delivery cannot be called anything else
    long_running = days is not None and days >= HORIZON_DAYS
    if read and comparable:
        # long on air, few people in all, and no fresh ad added to the concept: possibly forgotten
        newest = ad.get("newest_days") if ad.get("newest_days") is not None else days
        if long_running and (newest or 0) >= HORIZON_DAYS and small and scale <= LOW_SCALE:
            return "review"
        if scale >= HIGH_SCALE and leading and days is not None and SCALING_MIN_DAYS <= days < HORIZON_DAYS:
            return "scaling"
    if long_running and scale is not None and scale >= MID_SCALE:
        return "holding"
    if days is not None and days < TESTING_DAYS:
        return "testing"
    return "average"


def evaluate(ranked: list[dict], use_impressions: bool = True, library_total: int | None = None) -> list[dict]:
    """Rate every ad against the others in ``ranked`` and sort the list in place, best first.

    Call it again after reach has been read: ads with reach move to a high-reliability
    rating based on people reached per day, and the ads not opened get an estimate from
    their impression position, calibrated on the ones that were. ``library_total`` is how
    many ads the library lists for the search; ``use_impressions`` switches off the
    impression-position fallback where the list order cannot be trusted.
    """
    rates = [_market_reach(ad) for ad in ranked if _market_reach(ad)]
    everything_read = bool(rates) and len(rates) == len(ranked)
    reach_scale = len(rates) >= MIN_REACH_SAMPLE or everything_read
    # an ad of a few days is too recent to judge: it does not set the yardstick for the others
    settled = [_market_reach(ad) for ad in ranked if _market_reach(ad) and not too_recent(ad.get("days_running"))]
    best = max(settled or rates) if reach_scale else 0
    # zero counts: an ad read and found to reach nobody here is the weakest ad that was read
    lowest_read = min(rate for rate in map(_market_reach, ranked) if rate is not None) if reach_scale else 0
    estimate_reach = _reach_by_position(ranked) if reach_scale and use_impressions else None
    positions = [ad["impression_rank"] for ad in ranked if ad.get("impression_rank")]
    listed = max([library_total or 0, *positions, 1])

    rated = []
    for ad in ranked:
        days = ad.get("days_running")
        staying = round(100 * min(max(days or 0, 0) / HORIZON_DAYS, 1.0), 1)
        creative = round(100 * min(math.log(max(ad.get("creatives", 1), 1)) / math.log(FULL_CREATIVES), 1.0), 1)
        ad.pop("reach_per_day_estimate", None)
        rank = ad.get("impression_rank")
        if reach_scale and _market_reach(ad) is not None:
            scale, basis, reliability = _scale_from_rate(_market_reach(ad), best), "reach", "high"
        elif estimate_reach and rank:
            # never more than the weakest ad that was read: not reading an ad must not help it
            guess = min(estimate_reach(rank) / rate_days(ad.get("ad_days") if ad.get("ad_days") is not None else days),
                        lowest_read)
            ad["reach_per_day_estimate"] = round(guess)
            scale, basis, reliability = _scale_from_rate(guess, best), "impressions", "medium"
        elif use_impressions and rank:
            scale, basis, reliability = _scale_from_position(rank, listed), "impressions", "medium"
        else:
            scale, basis, reliability = None, None, "low"
        rated.append((ad, scale, basis, reliability, staying, creative))

    # labels that compare ads with each other rest on reach that was read, and on enough of it
    read = [(ad, scale) for ad, scale, _, reliability, *_ in rated if reliability == "high"]
    comparable = len(read) >= MIN_COMPARABLE
    scales = sorted((scale for _, scale in read), reverse=True)
    leading_from = scales[max(1, math.ceil(len(scales) / 3)) - 1] if scales else None
    totals = [ad["reach_total"] for ad, _ in read if ad.get("reach_total") is not None]
    middle_total = statistics.median(totals) if totals else 0

    for ad, scale, basis, reliability, staying, creative in rated:
        points = {"scale": round((scale or 0) * WEIGHTS["scale"] / 100, 1),
                  "staying": round(staying * WEIGHTS["staying"] / 100, 1),
                  "creative": round(creative * WEIGHTS["creative"] / 100, 1)}
        verdict = _verdict(ad, scale, reliability == "high", comparable,
                           leading=scale is not None and leading_from is not None and scale >= leading_from,
                           small=(ad.get("reach_total") or 0) < middle_total)
        ad.update(
            score=round(sum(points.values()), 1),
            score_parts={"scale": scale, "staying": staying, "creative": creative},
            score_points=points,
            score_weights=dict(WEIGHTS),
            scale_basis=basis,
            reliability=reliability,
            verdict=verdict,
            needs_review=verdict == "review",
            too_recent=too_recent(ad.get("days_running")),
        )
        if verdict == "review":
            ad["review"] = {"reason": "long_running_low_scale", "basis": basis}
        else:
            ad.pop("review", None)
    ranked.sort(key=lambda ad: (-ad["score"], -(ad["score_parts"]["scale"] or 0), -(ad.get("days_running") or 0),
                                ad["library_id"]))
    return ranked


def matches_query(ad: dict, query: str) -> bool:
    """Whether what is known of an ad contains every word of the keyword that was searched.

    The library matches a keyword against more than the visible text, so a miss here is
    a reason to look, not proof that the ad is off topic.
    """
    def plain(text: str) -> str:
        folded = unicodedata.normalize("NFKD", (text or "").casefold())
        return "".join(ch for ch in folded if not unicodedata.combining(ch))

    words = [word for word in _WORDS.findall(plain(query)) if len(word) >= 3]
    hay = plain(" ".join(str(ad.get(key) or "") for key in ("body", "headline", "description", "advertiser",
                                                            "landing_domain")))
    return all(word in hay for word in words)
