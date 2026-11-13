"""Command line: start the MCP server, export a report, or run the break-even check.

    ad-library-insights serve
    ad-library-insights report --country XX --query "<keyword>" [--advertiser NAME] --out DIR
    ad-library-insights breakeven --price 60 --product-cost 20 --csv ads.csv
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import breakeven, report, service
from .client import default_client


def _report(args: argparse.Namespace) -> int:
    result = asyncio.run(service.research(
        default_client(), args.query, args.country, args.advertiser, args.status,
        scroll_rounds=args.scroll_rounds, use_cache=not args.no_cache))
    if not result["ads"]:
        print(result.get("note", "No ads found."), file=sys.stderr)
        return 1
    files = report.write_report(result, service.copy_report(result, args.top), args.out, args.top)
    source = "cache" if result["from_cache"] else f"{result['attempts']} attempt(s)"
    print(f"{result['distinct_ads']} distinct ads from {len(result['advertisers'])} advertisers ({source})")
    for path in files.values():
        print(path)
    return 0


def _breakeven(args: argparse.Namespace) -> int:
    cpa = breakeven.breakeven_cpa(args.price, args.product_cost, args.shipping_cost,
                                  args.fee_pct, args.fee_fixed, args.other_costs)
    output = {"breakeven_cpa": cpa, "cut_threshold": round(cpa * args.multiplier, 2)}
    if args.csv:
        output["ads"] = breakeven.evaluate_ads(breakeven.load_ads_csv(args.csv), cpa, args.multiplier)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="ad-library-insights", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("serve", help="run the MCP server over stdio (default)")

    rep = commands.add_parser("report", help="research one search and write Markdown + CSV")
    rep.add_argument("--country", required=True, help="two-letter ISO country code, or ALL")
    rep.add_argument("--query", default="", help="keyword(s) to search")
    rep.add_argument("--advertiser", default="", help="keep advertisers whose name contains this")
    rep.add_argument("--status", default="active", choices=("active", "inactive", "all"))
    rep.add_argument("--top", type=int, default=10, help="ads to detail in the report")
    rep.add_argument("--scroll-rounds", type=int, default=6)
    rep.add_argument("--out", default="reports", help="output directory")
    rep.add_argument("--no-cache", action="store_true", help="ignore cached pages")

    be = commands.add_parser("breakeven", help="break-even CPA and cut list")
    be.add_argument("--price", type=float, required=True)
    be.add_argument("--product-cost", type=float, default=0)
    be.add_argument("--shipping-cost", type=float, default=0)
    be.add_argument("--fee-pct", type=float, default=0, help="payment fee, percent of price")
    be.add_argument("--fee-fixed", type=float, default=0)
    be.add_argument("--other-costs", type=float, default=0)
    be.add_argument("--multiplier", type=float, default=2.5)
    be.add_argument("--csv", default="", help="Ads Manager CSV export")

    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            return _report(args)
        if args.command == "breakeven":
            return _breakeven(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from .server import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
