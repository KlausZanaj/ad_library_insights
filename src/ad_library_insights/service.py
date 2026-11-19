"""The research pipeline shared by the MCP server and the CLI: fetch, filter, rank, analyse."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timezone

from . import consumption, copy_analysis, details, media, rating, signals
from .client import (AdLibraryClient, FetchResult, build_page_url, build_search_url,
                     normalise_country)
from .lab import anomalie, durata, ritmo, struttura

DEEP_CHOICES = (10, 20, 50)      # how many top ads to read reach for

OUTCOME_NOTES = {
    "no_results": "The Ad Library reports no ads for this search.",
    "blocked": "No ad cards were served after all retries. The page was probably refusing "
               "automated sessions; wait a few minutes before trying again.",
}


def advertiser_table(ranked: list[dict]) -> list[dict]:
    """Per-advertiser totals, heaviest advertisers first."""
    rows: dict[str, dict] = defaultdict(lambda: {"ads": 0, "oldest_start": None, "top_score": 0.0})
    for ad in ranked:
        row = rows[ad.get("advertiser") or "unknown"]
        row["ads"] += ad.get("copies_total", 1)
        row["top_score"] = max(row["top_score"], ad["score"])
        if ad.get("started") and (row["oldest_start"] is None or ad["started"] < row["oldest_start"]):
            row["oldest_start"] = ad["started"]
    return sorted(({"advertiser": name, **row} for name, row in rows.items()),
                  key=lambda r: (-r["ads"], -r["top_score"], r["advertiser"]))


def assemble(fetch: FetchResult, query: str, country: str, advertiser: str = "",
             as_of: date | None = None) -> dict:
    """Shape a fetch into the research result: filtered by advertiser, one ad per concept, rated."""
    ads = fetch.ads
    if advertiser:
        needle = advertiser.casefold()
        ads = [ad for ad in ads if needle in (ad.get("advertiser") or "").casefold()]
    ranked = signals.annotate(rating.group_concepts(ads, as_of), library_total=fetch.total_count)
    result = {
        "ok": fetch.ok,
        "outcome": fetch.outcome,
        "query": query,
        "country": country,
        "advertiser_filter": advertiser or None,
        "url": fetch.url,
        "results_label": fetch.results_label,
        "fetched_at": datetime.fromtimestamp(fetch.fetched_at, timezone.utc).isoformat(timespec="seconds")
                      if fetch.fetched_at else None,
        "from_cache": fetch.from_cache,
        "attempts": fetch.attempts,
        "source": fetch.source,
        "library_total": fetch.total_count,
        "ads_parsed": len(fetch.ads),
        "distinct_ads": len(ranked),
        "advertisers": advertiser_table(ranked),
        "signals": signals.summarize(ads, ranked, as_of, None if advertiser else fetch.total_count,
                                     country),
        "ads": ranked,
    }
    if not fetch.ok:
        result["note"] = OUTCOME_NOTES[fetch.outcome] + (f" Last error: {fetch.error}" if fetch.error else "")
    elif advertiser and not ranked:
        result["note"] = f'No advertiser matching "{advertiser}" among the {len(fetch.ads)} ads parsed.'
    return result


def refresh_structure(result: dict, snapshots: list[dict] | None = None) -> None:
    """Attach Su cosa si regge and Annunci fuori schema diagnostics to a result in place."""
    ads = result.get("ads") or []
    if not ads:
        return
    mode = result.get("mode") or "keyword"
    result["struttura"] = struttura.analyze(
        ads,
        result.get("signals"),
        mode=mode,
        country=result.get("country"),
        snapshots=snapshots,
    )
    result["anomalie"] = anomalie.select(ads, mode=mode)


async def research(client: AdLibraryClient, query: str, country: str, advertiser: str = "",
                   active_status: str = "active", media_type: str = "all",
                   wait_seconds: float = 8, scroll_rounds: int = 6, use_cache: bool = True,
                   as_of: date | None = None) -> dict:
    """Search by keyword and/or advertiser name in one country and rank what comes back.

    With only ``advertiser`` set, the advertiser name is used as the search term and
    the results are narrowed to advertisers whose name contains it.
    """
    term = (query or advertiser or "").strip()
    if not term:
        raise ValueError("pass a query, an advertiser name, or both")
    country = normalise_country(country)
    url = build_search_url(term, country, active_status, media_type)
    fetch = await client.fetch(url, wait_seconds=wait_seconds, scroll_rounds=scroll_rounds,
                               use_cache=use_cache)
    result = assemble(fetch, term, country, advertiser, as_of)
    if (query or "").strip():
        # the library matches a keyword against more than the visible text: say which ads do not show it
        for ad in result["ads"]:
            ad["query_match"] = rating.matches_query(ad, query)
        result["signals"]["off_query"] = sum(1 for ad in result["ads"] if not ad["query_match"])
    refresh_structure(result)
    return result


def copy_report(result: dict, top_n: int = 10) -> dict:
    """Copy breakdowns for the ``top_n`` best-ranked ads plus their shared patterns."""
    analyses = [copy_analysis.analyze_ad(ad) for ad in result["ads"][:max(1, top_n)]]
    return {"summary": copy_analysis.summarize(analyses), "ads": analyses}


def _page_from_ads(ads: list[dict], page_id: str) -> dict:
    first = next((ad for ad in ads if ad.get("page_id") == page_id), ads[0] if ads else {})
    return {"page_id": page_id, "name": first.get("advertiser"),
            "followers": first.get("page_likes"),
            "category": ", ".join(first.get("page_categories") or []) or None,
            "profile_url": first.get("advertiser_url"), "logo_url": first.get("logo_url")}


async def find_pages(client: AdLibraryClient, name: str, country: str,
                     use_cache: bool = True) -> dict:
    """Advertiser pages matching a name, most followed first, with the likeliest one marked."""
    country = normalise_country(country)
    pages = sorted(await client.find_pages(name, country, use_cache),
                   key=lambda p: -(p.get("followers") or 0))
    exact = [p for p in pages if (p.get("name") or "").casefold() == name.strip().casefold()]
    return {"ok": bool(pages), "name": name, "country": country, "pages": pages,
            "suggested_page_id": (exact or pages or [{}])[0].get("page_id")}


def _loaded_share(result: dict) -> float | None:
    found = result.get("signals") or {}
    listed = sum(ad.get("copies_total", 1) for ad in result.get("ads", []))
    active = found.get("active_ads")
    return round(min(listed / active, 1.0), 2) if active else None


async def research_company(client: AdLibraryClient, country: str, page_id: str = "",
                           name: str = "", active_status: str = "active",
                           scroll_rounds: int = 40, wait_seconds: float = 8,
                           use_cache: bool = True, as_of: date | None = None) -> dict:
    """Every active ad of one advertiser page in a country, ranked, with its signals.

    Pass ``page_id`` when the page is known. With only ``name`` the library is asked
    which pages carry that name: one match is used directly; with several the result
    has ``outcome: "choose_page"`` and the candidates, and nothing else is fetched.
    """
    country = normalise_country(country)
    chosen = None
    if not str(page_id or "").strip():
        if not (name or "").strip():
            raise ValueError("pass a page_id or an advertiser name")
        found = await find_pages(client, name, country, use_cache)
        if not found["pages"]:
            return {"ok": False, "outcome": "no_page", "name": name, "country": country,
                    "note": f'The Ad Library suggests no advertiser page for "{name}" in {country}.'}
        if len(found["pages"]) > 1:
            return {"ok": False, "outcome": "choose_page", "name": name, "country": country,
                    "pages": found["pages"], "suggested_page_id": found["suggested_page_id"],
                    "note": "Several pages match this name. Call again with the page_id of the one you mean."}
        chosen = found["pages"][0]
        page_id = chosen["page_id"]

    url = build_page_url(page_id, country, active_status)
    fetch = await client.fetch(url, wait_seconds=wait_seconds, scroll_rounds=scroll_rounds,
                               use_cache=use_cache)
    page = {**_page_from_ads(fetch.ads, str(page_id)), **{k: v for k, v in (chosen or {}).items() if v}}
    result = assemble(fetch, page.get("name") or name or str(page_id), country, as_of=as_of)
    result.update(mode="company", page=page)
    if active_status == "all" and result.get("ads"):
        result["durata"] = durata.analyze(
            result["ads"],
            mode="company",
            active_status="all",
            loaded_share=_loaded_share(result),
            as_of=as_of,
        )
    if result.get("ads"):
        result["ritmo"] = ritmo.analyze(
            result["ads"],
            mode="company",
            loaded_share=_loaded_share(result),
            as_of=as_of,
            durata_report=result.get("durata"),
            active_status=active_status,
        )
    refresh_structure(result)
    return result


async def analyze_durata(client: AdLibraryClient, country: str, page_id: str,
                         window_days: int = durata.DEFAULT_WINDOW_DAYS,
                         scroll_rounds: int = 40, wait_seconds: float = 8,
                         use_cache: bool = True, as_of: date | None = None) -> dict:
    """Load active and ended ads of one advertiser page and compute cohort Durata survival."""
    result = await research_company(client, country, page_id=page_id, active_status="all",
                                    scroll_rounds=scroll_rounds, wait_seconds=wait_seconds,
                                    use_cache=use_cache, as_of=as_of)
    cohort = (result["durata"]
              if "durata" in result and window_days == durata.DEFAULT_WINDOW_DAYS
              else durata.analyze(result.get("ads", []), mode="company", active_status="all",
                                  loaded_share=_loaded_share(result), window_days=window_days,
                                  as_of=as_of))
    ritmo_report = ritmo.analyze(
        result.get("ads", []),
        mode="company",
        loaded_share=_loaded_share(result),
        as_of=as_of,
        durata_report=cohort,
        active_status="all",
    )
    return {
        "ok": result.get("ok", False),
        "page": result.get("page"),
        "country": result.get("country"),
        "durata": cohort,
        "ritmo": ritmo_report,
    }


def estimate_deep(result: dict, top_n: int, frames: bool = False, ceiling: int | None = None) -> dict:
    """Time the reach reading will take for the ``top_n`` most shown concepts, before starting.

    ``ads`` is how many ads will be opened: one for each concept and, up to ``ceiling``,
    the second and third ad of the same concepts.
    """
    ceiling = rating.read_ceiling(top_n) if ceiling is None else ceiling
    targets = rating.cards_to_read(result["ads"], top_n, ceiling=ceiling)
    leads = [ad for ad, card_id in targets if card_id == ad["library_id"]]
    # stills are saved for the first concepts of the list only, as ``deepen`` does
    videos = min(sum(1 for ad in leads if ad.get("video_url")), consumption.ADS_WITH_FRAMES) if frames else 0
    return {"ads": len(targets), "concepts": len(leads), "videos": videos, "ceiling": ceiling,
            "seconds": details.estimate_seconds(len(targets), videos)}


async def deepen(client: AdLibraryClient, result: dict, top_n: int = 10, frames: bool = False,
                 on_progress=None, use_cache: bool = True, ceiling: int | None = None) -> dict:
    """Read reach and audience for the ``top_n`` most shown concepts of a result, in place.

    The concepts are taken in the order of the library's own list (total impressions),
    not by a rating that reach itself is about to change. The most shown ad of each is
    opened first. When one could not be opened, the second ad of that concept is tried;
    a concept of one ad only is replaced by the next concept of the list. Either is done
    once, so never more than ``top_n`` concepts are read. Only then, while the ceiling of
    ads opened allows
    (``rating.read_ceiling``), come the second and third ad of the same concepts: their
    reach is added up, so a concept split over many ads is not judged on one of them.
    A concept counts as read when at least one of its ads was opened. ``deep`` says how
    many concepts were read, how many ads were opened and whether the ceiling stopped
    the reading. Once reach is read the ads are rated again and the list is re-sorted.
    Thumbnails and page logos are saved locally at the same time; with ``frames`` three
    stills of each video are saved too, for the first ``consumption.ADS_WITH_FRAMES``
    concepts of the list.
    """
    ceiling = rating.read_ceiling(top_n) if ceiling is None else ceiling
    planned = len(rating.cards_to_read(result["ads"], top_n, ceiling=ceiling))
    chosen = rating.first_concepts(result["ads"], top_n)[:max(0, ceiling)]
    if not chosen:
        return result
    targets, outcomes, with_stills = [], {}, set()

    async def read(batch):
        heads = [ad for ad, card_id in batch if card_id == ad["library_id"]]
        clips = {}
        for ad in heads:                       # stills only for the first concepts of the list, as the estimate says
            if frames and ad.get("video_url") and len(with_stills) < consumption.ADS_WITH_FRAMES:
                with_stills.add(ad["library_id"])
                clips[ad["library_id"]] = ad["video_url"]
        already = len(targets)

        def report(event):                     # one count over the whole reading, not one per batch
            if on_progress:
                on_progress({**event, "done": already + event.get("done", 0),
                             "total": max(planned, already + event.get("total", 0))})

        outcomes.update(await client.read_details(result["url"], [card_id for _, card_id in batch],
                                                  result.get("country") or None, clips,
                                                  report if on_progress else None, use_cache))
        targets.extend(batch)

    def opened(card_id):
        return bool((outcomes.get(card_id) or {}).get("ok"))

    # 1. the most shown ad of every concept asked for
    await read([(ad, ad["library_id"]) for ad in chosen])
    # 2. a concept whose first ad could not be opened: its second ad is tried; a concept of one ad only is
    #    replaced by the next one of the list. Once, so the concepts read are never more than the ones asked for.
    second_try, to_replace = [], 0
    for ad in chosen:
        if not opened(ad["library_id"]) and len(targets) + len(second_try) + to_replace < ceiling:
            others = rating.other_cards(ad)
            if others:
                second_try.append((ad, others[0]["library_id"]))
            else:
                to_replace += 1
    replacements = rating.first_concepts(result["ads"], to_replace, skip={ad["library_id"] for ad in chosen})
    if second_try or replacements:
        await read(second_try + [(ad, ad["library_id"]) for ad in replacements])
    # 3. only then the second and third ad of those concepts, while the ceiling allows
    leads = [ad for ad, card_id in targets if card_id == ad["library_id"]]
    taken = {card_id for _, card_id in targets}
    extras = [(ad, card_id) for ad, card_id in rating.more_cards(leads, len(taken) + ceiling)
              if card_id not in taken][:max(0, ceiling - len(targets))]
    if extras:
        await read(extras)
    failed = []
    for ad, card_id in targets:
        outcome = outcomes.get(card_id) or {"ok": False, "error": "not read"}
        lead = card_id == ad["library_id"]
        if not outcome["ok"]:
            failed.append(card_id)
            if lead:
                ad["detail_error"] = outcome.get("error")
            continue
        found = outcome["details"]
        if lead:
            ad.update(reach=found["reach"], audience=found["audience"], payer=found["payer"])
            if result.get("mode") == "company" and found.get("page"):
                result["page"] = {**result.get("page", {}),
                                  **{k: v for k, v in found["page"].items() if v is not None}}
            ad.pop("detail_error", None)
            if outcome.get("frames"):
                ad["frames"] = outcome["frames"]
            if outcome.get("video_meta"):
                ad["video_meta"] = outcome["video_meta"]
        else:
            # another ad of the same concept: only its reach figures are kept
            ad.setdefault("card_reach", {})[card_id] = {
                key: found["reach"].get(key) for key in ("available", "country", "country_reach", "eu_total",
                                                         "uk_total", "countries_reached")}
    await asyncio.to_thread(media.save_ad_media, leads, client.media)
    if result.get("page", {}).get("logo_url") and result["page"].get("page_id"):
        result["page"]["logo_path"] = await asyncio.to_thread(
            client.media.save, result["page"]["logo_url"], f"page_{result['page']['page_id']}_logo")

    signals.annotate(result["ads"], library_total=result.get("library_total"))
    signals.refresh(result["signals"], result["ads"], result.get("country") or None)
    result["advertisers"] = advertiser_table(result["ads"])           # ratings changed with reach
    # a concept is read when at least one of its ads was opened; it has reach when one of them carries it
    with_reach = sum(1 for ad in leads if (ad.get("reach") or {}).get("available")
                     or any(found.get("available") for found in (ad.get("card_reach") or {}).values()))
    concepts_read = len({ad["library_id"] for ad, card_id in targets if opened(card_id)})
    left_out = rating.cards_left_out(targets)
    untried = len(rating.first_concepts(result["ads"], len(result["ads"]), skip={ad["library_id"] for ad in leads}))
    # the ceiling stopped something only if ads were left closed, or concepts asked for could still be tried
    capped = len(targets) >= ceiling and (left_out > 0 or (concepts_read < top_n and untried > 0))
    stopped = (f"Stopped at the ceiling of {ceiling} ads opened: {concepts_read} of the {top_n} concepts asked for "
               f"were read; {left_out} more ads of these concepts were left closed, so their reach is a floor."
               ) if capped else None
    result["deep"] = {"requested": top_n, "read": len(targets) - len(failed), "concepts": concepts_read,
                      "failed": failed, "with_reach": with_reach, "frames": bool(frames),
                      "ceiling": ceiling, "capped": capped, "left_out": left_out, "ceiling_note": stopped,
                      "note": None if with_reach or failed else details.NO_REACH_NOTE}
    refresh_structure(result)
    return result
