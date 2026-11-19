"""Reach and audience of single ads, read from their detail view.

Two parts:

* ``parse_details`` turns the response behind "See ad details" into reach, audience,
  chosen locations and advertiser page facts. Reach is read from whatever
  transparency sections the response contains; nothing assumes a list of countries.
  Meta publishes these sections for ads delivered in the European Union and in the
  United Kingdom. When an ad has none, the result says so instead of leaving a gap.
* ``DetailCollector`` opens many detail views in a row at a controlled pace: a pause
  between ads, a longer pause when answers get slow, retries with growing waits,
  an early stop when the page keeps refusing, and a progress report with the time left.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable

from . import records
from .storage import DiskCache

SECONDS_PER_AD = 2.0          # measured: open, read, close
SECONDS_PER_VIDEO = 1.5       # three frames
SESSION_START = 6.0           # loading the results page once

NO_REACH_NOTE = ("Meta publishes reach only for ads delivered in the European Union or the "
                 "United Kingdom. This ad has no such section.")


# Countries whose reach a section reports country by country. A country of the section
# that is missing from an ad's breakdown was not reached by that ad.
SECTION_COUNTRIES = {
    "EU": frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()),
    "UK": frozenset({"GB"}),
}


def _region_name(key: str) -> str:
    return key.split("_")[0].upper()


def _total(block: dict) -> int | None:
    for key, value in block.items():
        if key.endswith("total_reach") and isinstance(value, (int, float)):
            return int(value)
    return None


def _breakdown(block: dict) -> tuple[list[dict], dict[str, int], dict[str, int], list[dict]]:
    """Per-country totals, per-age totals, per-gender totals and 3D cells of one section."""
    countries, ages, genders = [], {}, {"male": 0, "female": 0, "unknown": 0}
    cells: dict[tuple[str | None, str], dict] = {}
    for row in block.get("age_country_gender_reach_breakdown") or []:
        country_code = row.get("country")
        country_total = 0
        for cell in row.get("age_gender_breakdowns") or []:
            age_range = cell.get("age_range") or "?"
            people = 0
            counts = {}
            for gender in genders:
                value = int(cell.get(gender) or 0)
                genders[gender] += value
                counts[gender] = value
                people += value
            ages[age_range] = ages.get(age_range, 0) + people
            country_total += people
            if people > 0:
                key = (country_code, age_range)
                bucket = cells.setdefault(
                    key, {"country": country_code, "age_range": age_range,
                          "male": 0, "female": 0, "unknown": 0, "reach": 0})
                for gender in genders:
                    bucket[gender] += counts[gender]
                bucket["reach"] += people
        countries.append({"country": country_code, "reach": country_total})
    countries.sort(key=lambda c: (-c["reach"], c["country"] or ""))
    return countries, ages, genders, list(cells.values())


def parse_reach(transparency: dict | None, country: str | None = None) -> dict:
    """Reach figures from every transparency section present.

    ``country`` is the country being researched; its own figure is taken from the
    per-country breakdown of whichever section lists it.
    """
    regions, by_age, by_gender = [], {}, {"male": 0, "female": 0, "unknown": 0}
    cells_3d: dict[tuple[str | None, str], dict] = {}
    for key, block in (transparency or {}).items():
        if not isinstance(block, dict):
            continue
        total = _total(block)
        countries, ages, genders, cells = _breakdown(block)
        if total is None and not countries:
            continue
        if total is not None and len(countries) == 1:
            countries[0]["reach"] = total      # one country: the same people as the section total
        regions.append({"region": _region_name(key),
                        "total": total if total is not None else sum(c["reach"] for c in countries),
                        "countries": countries})
        for age, people in ages.items():
            by_age[age] = by_age.get(age, 0) + people
        for gender, people in genders.items():
            by_gender[gender] += people
        for cell in cells:
            cell_key = (cell["country"], cell["age_range"])
            bucket = cells_3d.setdefault(
                cell_key, {"country": cell["country"], "age_range": cell["age_range"],
                           "male": 0, "female": 0, "unknown": 0, "reach": 0})
            for field in ("male", "female", "unknown", "reach"):
                bucket[field] += cell[field]

    if not regions:
        return {"available": False, "note": NO_REACH_NOTE, "regions": [], "country": country,
                "country_reach": None, "eu_total": None, "uk_total": None, "breakdown_3d": []}

    totals = {r["region"]: r["total"] for r in regions}
    wanted = (country or "").upper()
    if wanted == "ALL":
        wanted = ""
    country_reach = None
    for region in regions:
        row = next((c for c in region["countries"] if c["country"] == wanted), None)
        if row:
            # A section with one country describes the same people as its total; the sum
            # of its age and gender cells can differ from it by a few percent.
            country_reach = region["total"] if len(region["countries"]) == 1 else row["reach"]
            break
    if country_reach is None:
        for region in regions:
            if wanted in SECTION_COUNTRIES.get(region["region"], ()) and region["countries"]:
                country_reach = 0              # the section lists its countries and this one is not there
                break
    basis = "EU" if "EU" in totals else regions[0]["region"]
    breakdown_3d = sorted(cells_3d.values(), key=lambda c: (-c["reach"], c["country"] or "", c["age_range"]))
    return {
        "available": True,
        "regions": regions,
        "eu_total": totals.get("EU"),
        "uk_total": totals.get("UK"),
        "country": wanted or None,
        "country_reach": country_reach,
        "basis": basis,                       # the section the per-day figure is based on
        "basis_total": totals[basis],
        "countries_reached": sum(len(r["countries"]) for r in regions),
        "by_age": [{"age_range": age, "reach": people}
                   for age, people in sorted(by_age.items())],
        "by_gender": by_gender,
        "breakdown_3d": breakdown_3d,
    }


_PLACE_TYPES = {"country": "countries", "country_group": "country_groups", "region": "regions",
                "city": "cities", "zip": "zips", "postal_code": "zips"}


def _place_type(raw) -> str | None:
    """One spelling for location kinds; the page mixes "countries" with "CITY"."""
    kind = str(raw or "").strip().lower()
    return _PLACE_TYPES.get(kind, kind) or None


def parse_audience(transparency: dict | None) -> dict | None:
    """Targeting the advertiser chose: age, gender and locations, included and excluded.

    Locations are whatever the advertiser picked, so they can name countries or whole
    areas outside the regions for which reach is published.
    """
    blocks = [b for b in (transparency or {}).values() if isinstance(b, dict)]
    if not blocks:
        return None
    first = next((b for b in blocks if b.get("age_audience") or b.get("gender_audience")), blocks[0])
    age = first.get("age_audience") or {}
    locations, seen = [], set()
    for block in blocks:
        for place in block.get("location_audience") or []:
            key = (place.get("name"), place.get("type"), bool(place.get("excluded")))
            if place.get("name") and key not in seen:
                seen.add(key)
                locations.append({"name": place["name"], "type": _place_type(place.get("type")),
                                  "excluded": bool(place.get("excluded"))})
    return {
        "age_min": age.get("min"),
        "age_max": age.get("max"),
        "gender": first.get("gender_audience"),
        "locations_included": [l for l in locations if not l["excluded"]],
        "locations_excluded": [l for l in locations if l["excluded"]],
    }


def parse_page(details: dict) -> dict | None:
    info = records.find_key(details.get("advertiser") or {}, "page_info")
    if not isinstance(info, dict):
        return None
    about = records.find_key(details.get("advertiser") or {}, "about") or {}
    return {
        "page_id": str(info.get("page_id") or "") or None,
        "name": info.get("page_name"),
        "category": info.get("page_category"),
        "followers": info.get("likes"),
        "instagram": info.get("ig_username") or None,
        "instagram_followers": info.get("ig_followers"),
        "verified": info.get("page_verification") not in (None, "", "NOT_VERIFIED"),
        "profile_url": info.get("page_profile_uri"),
        "logo_url": info.get("profile_photo"),
        "about": about.get("text") if isinstance(about, dict) else None,
    }


def parse_details(payload, country: str | None = None) -> dict:
    """Everything the detail view adds to an ad: reach, audience, page, payer."""
    details = records.find_key(payload, "ad_details")
    if not isinstance(details, dict):
        raise ValueError("no ad details in this response")
    transparency = details.get("transparency_by_location")
    payers = (details.get("aaa_info") or {}).get("payer_beneficiary_data") or [{}]
    return {
        "reach": parse_reach(transparency, country),
        "audience": parse_audience(transparency),
        "page": parse_page(details),
        "payer": payers[0].get("payer"),
        "beneficiary": payers[0].get("beneficiary"),
    }


def estimate_seconds(ads: int, videos_with_frames: int = 0, pace: float = 1.0) -> int:
    """Rough time to read ``ads`` detail views, shown before the work starts."""
    if ads <= 0:
        return 0
    return round(SESSION_START + ads * (SECONDS_PER_AD + pace) + videos_with_frames * SECONDS_PER_VIDEO)


class DetailCollector:
    """Reads detail views one by one without hammering the page.

    * waits ``pace`` seconds (plus a little jitter) between ads;
    * doubles the pause, up to ``max_pace``, whenever an answer is slow or fails,
      and eases back after a run of quick answers;
    * retries a failed ad after ``retry_base`` seconds, tripling the wait each time;
    * gives up on the rest after ``stop_after`` ads in a row fail every retry, which
      is what a session that has been turned away looks like.

    ``session`` needs one method, ``async open(library_id) -> payload``. Sleeping,
    time and jitter are injectable so the policy can be tested without a browser.
    """

    def __init__(self, cache: DiskCache | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 jitter: Callable[[], float] = random.random,
                 pace: float = 1.0, max_pace: float = 8.0, slow_after: float = 5.0,
                 max_retries: int = 2, retry_base: float = 5.0, retry_factor: float = 3.0,
                 stop_after: int = 3):
        self.cache = cache
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self.base_pace = pace
        self.max_pace = max_pace
        self.slow_after = slow_after
        self.max_retries = max_retries
        self.retry_base = retry_base
        self.retry_factor = retry_factor
        self.stop_after = stop_after

    @staticmethod
    def cache_key(library_id: str, country: str | None) -> str:
        return f"details:{library_id}:{(country or '').upper()}"

    def cached(self, library_id: str, country: str | None) -> dict | None:
        hit = self.cache.get(self.cache_key(library_id, country)) if self.cache else None
        return hit.get("details") if hit else None

    async def collect(self, session, library_ids: list[str], country: str | None = None,
                      on_progress: Callable[[dict], None] | None = None,
                      use_cache: bool = True) -> dict[str, dict]:
        """``{library_id: {"ok", "details" | "error", "attempts", "from_cache"}}``."""
        results: dict[str, dict] = {}
        total = len(library_ids)
        started = self._clock()
        pace, quick_run, failed_run, fetched = self.base_pace, 0, 0, 0

        def report(library_id: str, status: str) -> None:
            if not on_progress:
                return
            done = len(results)
            elapsed = self._clock() - started
            # the pause before the next ad has not been slept yet, so count it in
            per_ad = (elapsed + pace) / fetched if fetched else SECONDS_PER_AD + pace
            on_progress({"done": done, "total": total, "library_id": library_id, "status": status,
                         "elapsed_seconds": round(elapsed, 1), "pace_seconds": round(pace, 2),
                         "eta_seconds": round(per_ad * (total - done))})

        for position, library_id in enumerate(library_ids):
            if use_cache:
                hit = self.cached(library_id, country)
                if hit is not None:
                    results[library_id] = {"ok": True, "details": hit, "attempts": 0, "from_cache": True}
                    report(library_id, "cached")
                    continue
            if failed_run >= self.stop_after:
                results[library_id] = {"ok": False, "error": "skipped: the page stopped answering",
                                       "attempts": 0, "from_cache": False}
                report(library_id, "skipped")
                continue
            if fetched:
                await self._sleep(pace * (1 + 0.3 * self._jitter()))

            outcome = {"ok": False, "error": None, "attempts": 0, "from_cache": False}
            for attempt in range(1, self.max_retries + 2):
                if attempt > 1:
                    await self._sleep(self.retry_base * self.retry_factor ** (attempt - 2))
                outcome["attempts"] = attempt
                began = self._clock()
                try:
                    payload = await session.open(library_id)
                    outcome.update(ok=True, error=None, details=parse_details(payload, country))
                except Exception as exc:  # timeouts, a card that vanished, a browser hiccup
                    outcome["error"] = f"{type(exc).__name__}: {exc}"
                took = self._clock() - began
                if outcome["ok"] and took <= self.slow_after:
                    quick_run += 1
                    if quick_run >= 5 and pace > self.base_pace:
                        pace, quick_run = max(self.base_pace, pace / 2), 0
                else:                      # slow or failed: back off before the next one
                    pace, quick_run = min(self.max_pace, pace * 2), 0
                if outcome["ok"]:
                    break

            fetched += 1
            failed_run = 0 if outcome["ok"] else failed_run + 1
            if outcome["ok"] and self.cache:
                self.cache.put(self.cache_key(library_id, country), {"details": outcome["details"]})
            results[library_id] = outcome
            report(library_id, "ok" if outcome["ok"] else "failed")
        return results
