"""The research pipeline shared by the MCP server and the CLI: fetch, filter, rank, analyse."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from . import copy_analysis, scoring
from .client import AdLibraryClient, FetchResult, build_search_url, normalise_country

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
        row["ads"] += ad.get("repetitions", 1)
        row["top_score"] = max(row["top_score"], ad["longevity_score"])
        if ad.get("started") and (row["oldest_start"] is None or ad["started"] < row["oldest_start"]):
            row["oldest_start"] = ad["started"]
    return sorted(({"advertiser": name, **row} for name, row in rows.items()),
                  key=lambda r: (-r["ads"], -r["top_score"], r["advertiser"]))


def assemble(fetch: FetchResult, query: str, country: str, advertiser: str = "",
             as_of: date | None = None) -> dict:
    """Shape a fetch into the research result: filtered by advertiser, ranked by longevity."""
    ads = fetch.ads
    if advertiser:
        needle = advertiser.casefold()
        ads = [ad for ad in ads if needle in (ad.get("advertiser") or "").casefold()]
    ranked = scoring.rank_ads(ads, as_of=as_of)
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
        "ads_parsed": len(fetch.ads),
        "distinct_ads": len(ranked),
        "advertisers": advertiser_table(ranked),
        "ads": ranked,
    }
    if not fetch.ok:
        result["note"] = OUTCOME_NOTES[fetch.outcome] + (f" Last error: {fetch.error}" if fetch.error else "")
    elif advertiser and not ranked:
        result["note"] = f'No advertiser matching "{advertiser}" among the {len(fetch.ads)} ads parsed.'
    return result


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
    return assemble(fetch, term, country, advertiser, as_of)


def copy_report(result: dict, top_n: int = 10) -> dict:
    """Copy breakdowns for the ``top_n`` best-ranked ads plus their shared patterns."""
    analyses = [copy_analysis.analyze_ad(ad) for ad in result["ads"][:max(1, top_n)]]
    return {"summary": copy_analysis.summarize(analyses), "ads": analyses}
