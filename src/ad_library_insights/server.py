"""MCP server: competitor ad research on the public Meta Ad Library."""
from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from . import breakeven, history, report, service
from .client import AdLibraryClient, default_client

mcp = FastMCP(
    name="Ad Library Insights",
    instructions=(
        "Research competitor ads in the public Meta Ad Library for any keyword, advertiser "
        "and country. Results are ranked by a longevity score (days running and copy reuse), "
        "the best ads can be broken down into hook, promise, proof and CTA, and everything "
        "can be exported to Markdown and CSV. A whole advertiser can be analysed by page: "
        "find_advertiser_pages lists the pages matching a name, analyze_company loads every "
        "active ad of the chosen page. Reach and audience are read from the detail view of the "
        "top-ranked ads only (deep_ads); Meta publishes them for ads delivered in the European "
        "Union or the United Kingdom, so say plainly when an ad has none. No spend or sales data "
        "exists for commercial ads: longevity is a proxy, say so when reporting. Searches are "
        "saved locally and what_changed compares the last two of the same keyword or page. Pages are "
        "cached for six hours and requests are spaced out, so a call can take a few minutes."
    ),
)

_client: AdLibraryClient | None = None


def _get_client() -> AdLibraryClient:
    global _client
    if _client is None:
        _client = default_client()
    return _client


def _trim(result: dict, max_results: int) -> dict:
    return {**result, "ads": result["ads"][:max(1, max_results)]}


def _progress_reporter():
    """Forward detail-reading progress to the MCP client, when it listens for it."""
    try:
        from fastmcp.server.dependencies import get_context
        context = get_context()
    except Exception:  # not inside a request, or an older FastMCP
        return None

    def report(event: dict) -> None:
        message = f"{event['done']}/{event['total']} ads read, about {event['eta_seconds']} s left"
        try:
            asyncio.ensure_future(context.report_progress(event["done"], event["total"], message))
        except Exception:
            pass

    return report


async def _deepen(result: dict, deep_ads: int, frames: bool, use_cache: bool) -> dict:
    if deep_ads > 0 and result.get("ads"):
        await service.deepen(_get_client(), result, deep_ads, frames, _progress_reporter(), use_cache)
    if result.get("ads"):       # remembered, so that what_changed has something to compare
        result["changes"] = history.summary(history.History().record(result))
    return result


@mcp.tool
async def search_ads(country: str, query: str = "", advertiser: str = "",
                     active_status: str = "active", media_type: str = "all",
                     max_results: int = 25, scroll_rounds: int = 6, wait_seconds: int = 8,
                     use_cache: bool = True, deep_ads: int = 0, frames: bool = False) -> dict:
    """Search the Ad Library and return ads ranked by longevity score.

    Args:
        country: two-letter ISO code of the country the ads are delivered in, or ALL.
        query: keyword(s): a product, a category, an angle. Optional if advertiser is set.
        advertiser: keep only advertisers whose name contains this text. Used as the
            search term when query is empty.
        active_status: active | inactive | all.
        media_type: all | image | meme | video | none.
        max_results: how many ranked ads to return.
        scroll_rounds: maximum scroll steps to load more ads (0 = first screen only).
        wait_seconds: longest wait for the first ads to appear.
        use_cache: set false to force a fresh fetch.
        deep_ads: read reach and audience for this many top-ranked ads (0 = none; 10, 20
            or 50 are sensible). About three seconds per ad.
        frames: also save three still frames of each video among those ads.
    """
    try:
        result = await service.research(
            _get_client(), query, country, advertiser, active_status, media_type,
            wait_seconds, scroll_rounds, use_cache)
        await _deepen(result, deep_ads, frames, use_cache)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return _trim(result, max_results)


@mcp.tool
async def find_advertiser_pages(name: str, country: str, use_cache: bool = True) -> dict:
    """List the advertiser pages the Ad Library suggests for a name.

    Returns each page with its id, followers and category, most followed first, and
    the likeliest match. When several pages share a name, show them and let the user
    choose before calling analyze_company.
    """
    try:
        return await service.find_pages(_get_client(), name, country, use_cache)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool
async def analyze_company(country: str, page_id: str = "", name: str = "", deep_ads: int = 10,
                          frames: bool = False, max_results: int = 25,
                          active_status: str = "active", scroll_rounds: int = 40,
                          use_cache: bool = True) -> dict:
    """Load every active ad of one advertiser page, rank it and compute its signals.

    Args:
        country: two-letter ISO code of the country the ads are delivered in.
        page_id: numeric id of the page (from find_advertiser_pages).
        name: advertiser name, used when page_id is empty. If several pages match,
            the result has outcome "choose_page" and lists them; nothing is loaded.
        deep_ads: read reach and audience for this many top-ranked ads (0, 10, 20, 50).
        frames: also save three still frames of each video among those ads.
        max_results: how many ranked ads to return.
        scroll_rounds: maximum scroll steps; 40 covers about 400 ads.

    The result carries "signals" (format mix, launches per week, languages, buttons,
    destinations, copy patterns, reach and audience summaries) and, per ad, tier,
    reach, audience, chosen locations and a needs_review flag.
    """
    try:
        result = await service.research_company(_get_client(), country, page_id, name,
                                                active_status, scroll_rounds, use_cache=use_cache)
        if "ads" not in result:
            return result
        await _deepen(result, deep_ads, frames, use_cache)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return _trim(result, max_results)


@mcp.tool
def what_changed(country: str = "", query: str = "", page_id: str = "") -> dict:
    """New, stopped and changed ads since the previous search of a keyword or company.

    Every search_ads and analyze_company call is saved on this machine; this compares
    the last two saved searches of the same keyword (query) or page (page_id) in a
    country. It needs two searches: after the first one it says so. Call it with no
    arguments to list what has been searched so far. To look for changes now, run the
    search again with use_cache false, then call this.
    """
    store = history.History()
    if not (query or page_id):
        return {"ok": True, "searches": store.subjects()}
    key = (f"company:{country.strip().upper()}:{page_id.strip()}" if page_id
           else f"keyword:{country.strip().upper()}:{query.strip().casefold()}")
    return {"ok": True, **store.changes(key)}


@mcp.tool
async def scrape_library_url(url: str, max_results: int = 25, scroll_rounds: int = 6,
                             wait_seconds: int = 8, use_cache: bool = True) -> dict:
    """Fetch an Ad Library URL you already have (any filters) and rank its ads."""
    try:
        fetch = await _get_client().fetch(url, wait_seconds, scroll_rounds, use_cache)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return _trim(service.assemble(fetch, query=url, country=""), max_results)


@mcp.tool
async def analyze_top_ads(country: str, query: str = "", advertiser: str = "", top_n: int = 10,
                          active_status: str = "active", use_cache: bool = True) -> dict:
    """Break the top-ranked ads into hook, promise, proof and CTA, with shared patterns.

    Same search arguments as search_ads. The breakdown is rule-based: treat it as a
    first pass to refine by reading the copy.
    """
    try:
        result = await service.research(_get_client(), query, country, advertiser,
                                        active_status, use_cache=use_cache)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not result["ads"]:
        return {k: v for k, v in result.items() if k != "ads"}
    return {"ok": True, "query": result["query"], "country": result["country"],
            "url": result["url"], **service.copy_report(result, top_n)}


@mcp.tool
async def export_report(country: str, output_dir: str, query: str = "", advertiser: str = "",
                        top_n: int = 10, formats: list[str] | None = None,
                        active_status: str = "active", use_cache: bool = True) -> dict:
    """Write a Markdown brief and/or a CSV of the ranked ads to output_dir.

    Args:
        formats: any of "markdown", "csv" (default: both).
    """
    try:
        result = await service.research(_get_client(), query, country, advertiser,
                                        active_status, use_cache=use_cache)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not result["ads"]:
        return {k: v for k, v in result.items() if k != "ads"}
    files = report.write_report(result, service.copy_report(result, top_n), output_dir, top_n,
                                tuple(formats or ("markdown", "csv")))
    return {"ok": True, "files": files, "distinct_ads": result["distinct_ads"],
            "advertisers": len(result["advertisers"])}


@mcp.tool
def check_breakeven_cpa(price: float, product_cost: float = 0, shipping_cost: float = 0,
                        payment_fee_pct: float = 0, payment_fee_fixed: float = 0,
                        other_costs: float = 0, multiplier: float = 2.5,
                        ads: list[dict] | None = None, csv_path: str = "") -> dict:
    """Compute break-even CPA and flag ads to cut.

    An ad is flagged "cut" once it has spent `multiplier` times the break-even CPA
    (2-3 is the usual range) with no add to cart and no purchase.

    Args:
        ads: rows like {"name": str, "spend": number, "add_to_cart": number, "purchases": number}.
        csv_path: alternatively, an Ads Manager CSV export to read the rows from.
    """
    try:
        cpa = breakeven.breakeven_cpa(price, product_cost, shipping_cost, payment_fee_pct,
                                      payment_fee_fixed, other_costs)
        rows = breakeven.load_ads_csv(csv_path) if csv_path else (ads or [])
        judged = breakeven.evaluate_ads(rows, cpa, multiplier) if rows else []
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "breakeven_cpa": cpa, "cut_threshold": round(cpa * multiplier, 2),
            "multiplier": multiplier, "to_cut": [r["name"] for r in judged if r["verdict"] == "cut"],
            "ads": judged}


def run() -> None:
    mcp.run(transport="stdio")
