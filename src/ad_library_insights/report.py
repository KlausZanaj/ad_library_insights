"""Export a research result as a Markdown brief and a CSV table."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date
from pathlib import Path

from . import copy_analysis

CSV_COLUMNS = [
    "rank", "longevity_score", "days_running", "repetitions", "creative_variants",
    "advertiser", "status", "started", "media_type", "cta", "landing_domain", "headline",
    "hook_type", "hook", "promise", "proof_kinds", "body", "library_id", "ad_url",
]


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-") or "report"


def _cell(value, limit: int = 0) -> str:
    """Make a value safe for one Markdown table cell."""
    text = " ".join(str(value if value is not None else "").split()).replace("|", "\\|")
    return text[:limit - 1].rstrip() + "…" if limit and len(text) > limit else text


def _percent(share: float) -> str:
    return f"{round(share * 100)}%"


def _counts(counter: dict) -> str:
    return ", ".join(f"{key} ({count})" for key, count in counter.items()) or "none"


def csv_rows(ads: list[dict]) -> list[dict]:
    rows = []
    for rank, ad in enumerate(ads, start=1):
        breakdown = copy_analysis.analyze_ad(ad)
        rows.append({
            **{column: ad.get(column) for column in CSV_COLUMNS},
            "rank": rank,
            "hook_type": breakdown["hook"]["type"] if breakdown["hook"] else "",
            "hook": breakdown["hook"]["text"] if breakdown["hook"] else "",
            "promise": breakdown["promise"]["text"] if breakdown["promise"] else "",
            "proof_kinds": ";".join(sorted({k for item in breakdown["proof"] for k in item["kinds"]})),
        })
    return rows


def to_csv(ads: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv_rows(ads))
    return buffer.getvalue()


def to_markdown(result: dict, copy: dict, top_n: int = 10, generated_on: date | None = None) -> str:
    """Render the brief. ``copy`` is the output of ``service.copy_report``."""
    generated_on = generated_on or date.today()
    ads, summary = result["ads"], copy["summary"]
    scope = f'"{result["query"]}" in {result["country"]}'
    if result.get("advertiser_filter"):
        scope += f', advertiser containing "{result["advertiser_filter"]}"'

    out = [
        f"# Ad Library report: {scope}",
        "",
        f"- Generated: {generated_on.isoformat()}",
        f"- Library total for this search: {result.get('results_label') or 'not shown'}",
        f"- Ads parsed: {result['ads_parsed']} ({result['distinct_ads']} after merging identical copy)",
        f"- Advertisers: {len(result['advertisers'])}",
        f"- Source: <{result['url']}>",
        "",
        "## Top advertisers",
        "",
        "| Advertiser | Ads with this search | Oldest start | Best score |",
        "|---|---:|---|---:|",
    ]
    for row in result["advertisers"][:top_n]:
        out.append(f"| {_cell(row['advertiser'])} | {row['ads']} | {row['oldest_start'] or '-'} "
                   f"| {row['top_score']} |")

    out += [
        "",
        "## Longest-running ads",
        "",
        "Ranked by longevity score (days running and copy reuse; see Method).",
        "",
        "| # | Score | Days | Reuse | Advertiser | Opening line | CTA | Ad |",
        "|---:|---:|---:|---:|---|---|---|---|",
    ]
    for rank, ad in enumerate(ads[:top_n], start=1):
        opening = (ad.get("body") or ad.get("headline") or "").split("\n")[0]
        days = ad["days_running"] if ad["days_running"] is not None else "-"
        out.append(f"| {rank} | {ad['longevity_score']} | {days} "
                   f"| {ad['repetitions']} | {_cell(ad.get('advertiser'))} | {_cell(opening, 90)} "
                   f"| {_cell(ad.get('cta'))} | [{ad['library_id']}]({ad['ad_url']}) |")

    out += [
        "",
        f"## Copy patterns in the top {summary['ads_analyzed']}",
        "",
        f"- Hook types: {_counts(summary['hook_types'])}",
        f"- Ads with proof: {_percent(summary['share_with_proof'])} ({_counts(summary['proof_kinds'])})",
        f"- CTA buttons: {_counts(summary['cta_buttons'])}",
        f"- Closing line that asks for the action: {_percent(summary['share_with_closing_line'])}",
        f"- Urgency near the end: {_percent(summary['share_with_urgency'])}",
        f"- Mention a price: {_percent(summary['share_mentioning_price'])}; "
        f"mention an offer: {_percent(summary['share_mentioning_offer'])}",
        f"- Use emoji: {_percent(summary['share_with_emoji'])}; "
        f"median length: {summary['median_characters']} characters",
        f"- Most common structures: {_counts(summary['common_structures'])}",
        "",
        "## Copy breakdown",
    ]
    for rank, (ad, item) in enumerate(zip(ads, copy["ads"]), start=1):
        proof = "; ".join(f"{_cell(p['text'], 160)} ({', '.join(p['kinds'])})" for p in item["proof"])
        cta = item["cta"]
        days = f"{ad['days_running']} days" if ad["days_running"] is not None else "start date unknown"
        out += [
            "",
            f"### {rank}. {_cell(ad.get('advertiser') or 'Unknown advertiser')} "
            f"(score {ad['longevity_score']}, {days})",
            "",
            f"- **Hook** ({item['hook']['type']}): {_cell(item['hook']['text'], 240)}"
            if item["hook"] else "- **Hook**: no body copy",
            f"- **Promise**: {_cell(item['promise']['text'], 240) if item['promise'] else 'none found'}",
            f"- **Proof**: {proof or 'none found'}",
            f"- **CTA**: button \"{cta['button'] or 'none'}\""
            + (f"; closing line: {_cell(cta['closing_line'], 160)}" if cta["closing_line"] else "")
            + ("; urgency" if cta["urgency"] else ""),
            f"- **Headline**: {_cell(item['headline'], 160) or 'none'}",
            f"- [Open in the Ad Library]({ad['ad_url']})",
        ]

    out += [
        "",
        "## Method and limits",
        "",
        "- Data is what the public Ad Library page showed at generation time, for one keyword "
        "search and one country. It is a sample of the matching ads, not all of them.",
        "- The longevity score (0-100) blends days running (60%, capped at 90 days) with how many "
        "ads reuse the same copy (40%, capped at 10). It is a proxy for what an advertiser keeps "
        "paying for. The Ad Library publishes no spend, reach or conversions for commercial ads.",
        "- Hook, promise, proof and CTA are assigned by rules (position, punctuation, digits and "
        "a multilingual phrase list). Read them as a first pass and check the linked ad.",
        "",
    ]
    return "\n".join(out)


def write_report(result: dict, copy: dict, output_dir: str | Path, top_n: int = 10,
                 formats: tuple[str, ...] = ("markdown", "csv"),
                 generated_on: date | None = None) -> dict[str, str]:
    """Write the requested files and return their paths keyed by format."""
    generated_on = generated_on or date.today()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    parts = [result["query"], result["country"]]
    if result.get("advertiser_filter") and result["advertiser_filter"] != result["query"]:
        parts.insert(1, result["advertiser_filter"])
    stem = f"{slugify(' '.join(parts))}-{generated_on.isoformat()}"
    written = {}
    if "markdown" in formats:
        path = directory / f"{stem}.md"
        path.write_text(to_markdown(result, copy, top_n, generated_on), encoding="utf-8")
        written["markdown"] = str(path)
    if "csv" in formats:
        path = directory / f"{stem}.csv"
        path.write_text(to_csv(result["ads"]), encoding="utf-8-sig", newline="")
        written["csv"] = str(path)
    return written
