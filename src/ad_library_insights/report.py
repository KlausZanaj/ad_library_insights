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
    "rank", "score", "verdict", "reliability", "kind", "needs_review", "impression_rank", "days_running",
    "creatives", "cards", "copies_total", "languages", "longevity_score", "advertiser", "status", "started", "media_type", "platforms", "cta",
    "landing_domain", "headline", "hook_type", "hook", "promise", "proof_kinds",
    "reach_eu", "reach_country", "reach_ads_read", "reach_uk", "reach_per_day", "age_min", "age_max", "gender",
    "locations_included", "locations_excluded", "body", "library_id", "ad_url",
]


VERDICTS = {"scaling": "Scaling", "holding": "Holding up", "testing": "Testing", "review": "Check",
            "average": "Average", "ended": "Ended"}


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


def _number(value) -> str:
    return f"{value:,}" if isinstance(value, (int, float)) else "-"


def _reach_cells(ad: dict) -> dict:
    """Flat reach and audience columns; empty when the detail view was not read."""
    reach, audience = ad.get("reach") or {}, ad.get("audience") or {}
    names = lambda places: ";".join(place["name"] for place in places or [])  # noqa: E731
    return {
        "platforms": ";".join(ad.get("platforms") or []),
        "needs_review": "yes" if ad.get("needs_review") else "",
        "languages": ";".join(ad.get("languages") or []),
        "reach_eu": reach.get("eu_total"),
        "reach_country": ad.get("reach_total"),       # the concept's ads that were read, added up
        "reach_ads_read": ad.get("reach_cards_read"),
        "reach_uk": reach.get("uk_total"),
        "reach_per_day": ad.get("reach_per_day"),     # in the country searched, over seven days at least
        "age_min": audience.get("age_min"),
        "age_max": audience.get("age_max"),
        "gender": audience.get("gender"),
        "locations_included": names(audience.get("locations_included")),
        "locations_excluded": names(audience.get("locations_excluded")),
    }


def _signal_lines(result: dict) -> list[str]:
    """The code-computed signals of a search or advertiser, as Markdown."""
    found = result.get("signals")
    if not found:
        return []
    formats = ", ".join(f"{name} {_percent(share)}" for name, share in found["format_share"].items())
    top = lambda rows, key: ", ".join(f"{r[key]} ({r['ads']})" for r in rows[:5]) or "none"  # noqa: E731
    out = [
        "",
        "## Signals",
        "",
        f"- Active ads: {_number(found['active_ads'])} in the library, {found['ads_loaded']} loaded here",
        f"- Formats: {formats or 'unknown'}",
        f"- New ads per week (last four weeks): {found['new_per_week']}; "
        f"started in the last 30 days: {found['started_last_30_days']} "
        f"({_percent(found['share_started_last_30_days'])})",
        f"- Languages: {top(found['languages'], 'language')}",
        f"- Buttons: {top(found['buttons'], 'button')}",
        f"- Destinations: {top(found['destinations'], 'domain')}",
        f"- Platforms: {top(found['platforms'], 'platform')}",
        f"- Verdicts: {_counts(found['verdicts'])}; rating reliability: {_counts(found['reliability'])}",
    ]
    reach = found["reach"]
    if reach.get("available"):
        out += [
            f"- Reach per ad in {reach.get('country') or 'the market'}: median {_number(reach['median_reach_per_day'])} "
            f"people per day ({_number(reach.get('median_reach_total'))} in total), best "
            f"{_number(reach['highest_reach_per_day'])} per day ({_number(reach.get('highest_reach_total'))} in total); "
            f"{reach.get('ads_with_market_reach', 0)} of the {reach['ads_with_reach']} ads with published reach were reached there. "
            "Figures are unique people per ad and are not added up: one person can see several ads",
        ]
    else:
        out.append(f"- Reach: {reach['note']}")
    audience = found.get("audience")
    if audience:
        places = lambda rows: ", ".join(f"{r['name']} ({r['ads']})" for r in rows[:12]) or "none"  # noqa: E731
        ages = ", ".join(f"{r['age_min']}-{r['age_max']} ({r['ads']})" for r in audience["age_ranges"])
        out += [
            f"- Audience: ages {ages}; gender {_counts(audience['genders'])}; breadth {_counts(audience['breadth'])}",
            f"- Locations targeted: {places(audience['locations_included'])}",
            f"- Locations excluded: {places(audience['locations_excluded'])}",
        ]
    return out


def _reach_table(ads: list[dict], country: str) -> list[str]:
    read = [ad for ad in ads if "reach" in ad]
    if not read:
        return []
    out = [
        "",
        "## Reach and audience of the top ads",
        "",
        "Reach is published by Meta for ads delivered in the European Union and the United "
        "Kingdom. Locations are what the advertiser targeted and can include other areas.",
        "",
        f"| # | Advertiser | Days | {country or 'Country'} reach | Per day in {country or 'country'} | EU reach | UK reach | Age | Gender | Ad |",
        "|---:|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for rank, ad in enumerate(ads, start=1):
        if "reach" not in ad:
            continue
        reach, audience = ad["reach"], ad.get("audience") or {}
        age = f"{audience.get('age_min')}-{audience.get('age_max')}" if audience else "-"
        flag = " (review)" if ad.get("needs_review") else ""
        out.append(
            f"| {rank} | {_cell(ad.get('advertiser'))}{flag} | {ad.get('days_running', '-')} "
            f"| {_number(ad.get('reach_total')) if reach.get('available') else 'not published'} "
            f"| {_number(ad.get('reach_per_day'))} | {_number(reach.get('eu_total'))} "
            f"| {_number(reach.get('uk_total'))} | {age} | {audience.get('gender') or '-'} "
            f"| [{ad['library_id']}]({ad['ad_url']}) |")
    return out


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
            **_reach_cells(ad),
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
        "## Top ads",
        "",
        "Rated on scale, staying power and creative investment (see Method).",
        "",
        "| # | Rating | Verdict | Reliability | Reached | Per day | Days | Creatives | Advertiser | Opening line | Ad |",
        "|---:|---:|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for rank, ad in enumerate(ads[:top_n], start=1):
        opening = (ad.get("body") or ad.get("headline") or "").split("\n")[0]
        days = ad["days_running"] if ad["days_running"] is not None else "-"
        kind = f" ({ad['kind']})" if ad.get("kind") not in (None, "standard") else ""
        out.append(f"| {rank} | {ad['score']} | {VERDICTS.get(ad['verdict'], ad['verdict'])} | {ad['reliability']} "
                   f"| {_number(ad.get('reach_total'))} | {_number(ad.get('reach_per_day'))} | {days} "
                   f"| {ad.get('creatives', 1)}{kind} "
                   f"| {_cell(ad.get('advertiser'))} | {_cell(opening, 80)} "
                   f"| [{ad['library_id']}]({ad['ad_url']}) |")

    out += _signal_lines(result)
    out += _reach_table(ads[:top_n], result.get("country") or "")
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
            f"(rating {ad['score']}, {VERDICTS.get(ad['verdict'], ad['verdict'])}, {days})",
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
        "- The rating (0-100) adds three parts: scale (people reached per day in the country "
        "searched, or the position by impressions where that is not published; up to 60 points), "
        "staying power (days running, full at 90; up to 25) and creative investment (different "
        "creatives carrying the same concept, full at 10; up to 15). Scale is measured against the "
        "best ad of this search: 100 for it, 0 for an ad reaching a thousand times fewer people. "
        "Reliability is high when reach in the country searched was read, medium when only the "
        "impression position is known, low otherwise.",
        "- Reach per day divides the people reached in the country searched by the days the ad has "
        "been on air, seven at the least; an ad younger than seven days is too recent to judge. "
        "Reach counts unique people, who grow slower than days: an ad on air for months shows "
        "fewer people per day than it really had, so the total reached is printed beside it.",
        "- Identical copies, versions of one dynamic ad, catalogue ads and translations of the same "
        "ad are grouped into one ad with variants and do not count as creative investment.",
        "- The Ad Library publishes no spend or sales for commercial ads, and reach only for ads "
        "delivered in the European Union or the United Kingdom. \"Check\" marks ads that ran long "
        "and reach far fewer people per day than the other ads here: a small budget that works or "
        "a forgotten ad. It asks for a look, it is not a negative verdict.",
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
