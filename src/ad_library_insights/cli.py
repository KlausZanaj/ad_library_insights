"""Command line: open the local app, start the MCP server, export a report, or run the break-even check.

    ad-library-insights app
    ad-library-insights serve
    ad-library-insights report --country XX --query "<keyword>" [--advertiser NAME] --out DIR
    ad-library-insights pages --country XX --name "<advertiser>"
    ad-library-insights company --country XX --name "<advertiser>" [--page-id ID] --deep 10 --out DIR
    ad-library-insights breakeven --price 60 --product-cost 20 --csv ads.csv
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import breakeven, history, link, report, service, video
from .client import default_client


def _duration(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60} min {seconds % 60:02d} s" if seconds >= 60 else f"{seconds} s"


def _show_progress(event: dict) -> None:
    """One line per ad on stderr: how many are done and how long is left."""
    print(f"  {event['done']}/{event['total']} ads read ({event['status']}), "
          f"about {_duration(event['eta_seconds'])} left", file=sys.stderr, flush=True)


async def _deepen(client, result: dict, args: argparse.Namespace) -> None:
    if args.deep <= 0 or not result.get("ads"):
        return
    plan = service.estimate_deep(result, args.deep, args.frames)
    print(f"Reading reach and audience of the {plan['concepts']} most shown concepts ({plan['ads']} ads to open, "
          f"ceiling {plan['ceiling']}): about {_duration(plan['seconds'])}.", file=sys.stderr, flush=True)
    await service.deepen(client, result, args.deep, args.frames, _show_progress, not args.no_cache)
    deep = result["deep"]
    print(f"Read {deep['concepts']} concepts ({deep['read']} ads opened); {deep['with_reach']} with reach published"
          + (f"; failed: {', '.join(deep['failed'])}" if deep["failed"] else "") + ".", file=sys.stderr)
    if deep.get("ceiling_note"):
        print(deep["ceiling_note"], file=sys.stderr)


def _finish(result: dict, args: argparse.Namespace) -> int:
    if not result.get("ads"):
        print(result.get("note", "No ads found."), file=sys.stderr)
        return 1
    files = report.write_report(result, service.copy_report(result, args.top), args.out, args.top)
    source = "cache" if result["from_cache"] else f"{result['attempts']} attempt(s)"
    print(f"{result['distinct_ads']} distinct ads from {len(result['advertisers'])} advertisers ({source})")
    changes = history.History().record(result)
    if changes.get("available"):
        counts = changes["counts"]
        print(f"Since {changes['previous']['taken_at']}: {counts['new']} new, {counts['stopped']} stopped, "
              f"{counts['changed']} changed")
    else:
        print("First saved search: changes will show from the next one.")
    for path in files.values():
        print(path)
    return 0


def _report(args: argparse.Namespace) -> int:
    async def run() -> dict:
        client = default_client()
        result = await service.research(
            client, args.query, args.country, args.advertiser, args.status,
            scroll_rounds=args.scroll_rounds, use_cache=not args.no_cache)
        await _deepen(client, result, args)
        return result
    return _finish(asyncio.run(run()), args)


def _print_pages(pages: list[dict], suggested: str | None) -> None:
    for page in pages:
        followers = f"{page['followers']:,}" if page.get("followers") is not None else "?"
        mark = "  <- likeliest" if page["page_id"] == suggested else ""
        print(f"{page['page_id']:>18}  {page.get('name') or '?'}  "
              f"({followers} followers, {page.get('category') or 'no category'}){mark}")


def _pages(args: argparse.Namespace) -> int:
    found = asyncio.run(service.find_pages(default_client(), args.name, args.country, not args.no_cache))
    if not found["pages"]:
        print(f'No advertiser page suggested for "{args.name}" in {found["country"]}.', file=sys.stderr)
        return 1
    _print_pages(found["pages"], found["suggested_page_id"])
    return 0


def _company(args: argparse.Namespace) -> int:
    async def run() -> dict:
        client = default_client()
        result = await service.research_company(
            client, args.country, args.page_id, args.name, args.status,
            scroll_rounds=args.scroll_rounds, use_cache=not args.no_cache)
        await _deepen(client, result, args)
        return result
    result = asyncio.run(run())
    if result.get("outcome") == "choose_page":
        print("Several pages match this name. Run again with --page-id:", file=sys.stderr)
        _print_pages(result["pages"], result["suggested_page_id"])
        return 3
    return _finish(result, args)


def _breakeven(args: argparse.Namespace) -> int:
    cpa = breakeven.breakeven_cpa(args.price, args.product_cost, args.shipping_cost,
                                  args.fee_pct, args.fee_fixed, args.other_costs)
    output = {"breakeven_cpa": cpa, "cut_threshold": round(cpa * args.multiplier, 2)}
    if args.csv:
        output["ads"] = breakeven.evaluate_ads(breakeven.load_ads_csv(args.csv), cpa, args.multiplier)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def _video(args: argparse.Namespace) -> int:
    result = asyncio.run(video.inspect_video(
        args.ad_id,
        pack_folder=args.pack or None,
        transcribe=args.transcribe,
        whisper_model=args.model,
        language=args.language or None,
        use_cache=not args.no_cache,
    ))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _video_setup(args: argparse.Namespace) -> int:
    result = video.setup_whisper_model(args.model)
    if not result.get("ok"):
        print(result.get("note", "Could not prepare Whisper model."), file=sys.stderr)
        return 1
    print(result.get("note", f"Model {args.model} ready."))
    return 0


def _connect(args: argparse.Namespace) -> int:
    out: dict = {}
    ok = True
    if args.claude or not args.antigravity:
        res = link.connect(link.Settings(), overwrite_skills=args.overwrite)
        out["claude"] = res
        ok = ok and bool(res.get("ok"))
    if args.antigravity:
        ag = link.connect_antigravity(overwrite=args.overwrite)
        out["antigravity"] = ag
        ok = ok and bool(ag.get("ok"))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="ad-library-insights", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("serve", help="run the MCP server over stdio (default)")

    web = commands.add_parser("app", help="open the local web app in the browser")
    web.add_argument("--port", type=int, default=8765, help="preferred port on 127.0.0.1")
    web.add_argument("--no-browser", action="store_true", help="do not open the browser")

    rep = commands.add_parser("report", help="research one search and write Markdown + CSV")
    rep.add_argument("--country", required=True, help="two-letter ISO country code, or ALL")
    rep.add_argument("--query", default="", help="keyword(s) to search")
    rep.add_argument("--advertiser", default="", help="keep advertisers whose name contains this")
    rep.add_argument("--status", default="active", choices=("active", "inactive", "all"))
    rep.add_argument("--top", type=int, default=10, help="ads to detail in the report")
    rep.add_argument("--scroll-rounds", type=int, default=6)
    rep.add_argument("--out", default="reports", help="output directory")
    rep.add_argument("--no-cache", action="store_true", help="ignore cached pages")
    rep.add_argument("--deep", type=int, default=0,
                     help="read reach and audience for this many of the most shown concepts (10, 20, 50)")
    rep.add_argument("--frames", action="store_true", help="save three stills of each video too")

    pag = commands.add_parser("pages", help="list the advertiser pages matching a name")
    pag.add_argument("--country", required=True, help="two-letter ISO country code")
    pag.add_argument("--name", required=True, help="advertiser name to look up")
    pag.add_argument("--no-cache", action="store_true", help="ignore cached lookups")

    com = commands.add_parser("company", help="analyse every active ad of one advertiser page")
    com.add_argument("--country", required=True, help="two-letter ISO country code")
    com.add_argument("--name", default="", help="advertiser name (looked up when --page-id is not given)")
    com.add_argument("--page-id", default="", help="numeric id of the page, from the pages command")
    com.add_argument("--status", default="active", choices=("active", "inactive", "all"))
    com.add_argument("--deep", type=int, default=10,
                     help="read reach and audience for this many of the most shown concepts (0, 10, 20, 50)")
    com.add_argument("--frames", action="store_true", help="save three stills of each video too")
    com.add_argument("--top", type=int, default=10, help="ads to detail in the report")
    com.add_argument("--scroll-rounds", type=int, default=40)
    com.add_argument("--out", default="reports", help="output directory")
    com.add_argument("--no-cache", action="store_true", help="ignore cached pages")

    be = commands.add_parser("breakeven", help="break-even CPA and cut list")
    be.add_argument("--price", type=float, required=True)
    be.add_argument("--product-cost", type=float, default=0)
    be.add_argument("--shipping-cost", type=float, default=0)
    be.add_argument("--fee-pct", type=float, default=0, help="payment fee, percent of price")
    be.add_argument("--fee-fixed", type=float, default=0)
    be.add_argument("--other-costs", type=float, default=0)
    be.add_argument("--multiplier", type=float, default=2.5)
    be.add_argument("--csv", default="", help="Ads Manager CSV export")

    vid = commands.add_parser("video", help="inspect a single video ad on demand")
    vid.add_argument("--ad-id", required=True, help="numeric Ad Library ID")
    vid.add_argument("--pack", default="", help="optional analysis or plan pack folder")
    vid.add_argument("--transcribe", action="store_true",
                     help="transcribe speech offline via optional .[video] extras")
    vid.add_argument("--model", default=video.DEFAULT_WHISPER_MODEL, choices=video.WHISPER_MODELS,
                     help="local Whisper model size")
    vid.add_argument("--language", default="", help="optional ISO language hint (e.g. it, en)")
    vid.add_argument("--no-cache", action="store_true", help="re-capture frames instead of using cache")

    vsetup = commands.add_parser("video-setup", help="pre-download local Whisper model for offline transcription")
    vsetup.add_argument("--model", default=video.DEFAULT_WHISPER_MODEL, choices=video.WHISPER_MODELS,
                        help="Whisper model size to download locally")

    con = commands.add_parser("connect", help="register the MCP server and copy skills/sub-agents")
    con.add_argument("--claude", action="store_true", help="configure Claude Code MCP server and skills/agents")
    con.add_argument("--antigravity", action="store_true", help="configure Google Antigravity MCP server and skills")
    con.add_argument("--overwrite", action="store_true", help="overwrite modified skill/agent files")

    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            return _report(args)
        if args.command == "breakeven":
            return _breakeven(args)
        if args.command == "pages":
            return _pages(args)
        if args.command == "app":
            from .web.app import serve
            serve(args.port, not args.no_browser)
            return 0
        if args.command == "company":
            return _company(args)
        if args.command == "video":
            return _video(args)
        if args.command == "video-setup":
            return _video_setup(args)
        if args.command == "connect":
            return _connect(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from .server import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
