"""Turn a research result into a data pack an assistant can read: one file per specialist.

Plain code, no model. The Analysis and Plan levels hand the collected data to the
user's own assistant; to keep that cheap, the data is cut into slices, so that a
specialist looking at copy never has to read reach tables, and the other way round:

    overview.md   what was collected, how the score works, what the data cannot say
    copy.md       the texts of the top ads and the patterns across all texts
    creative.md   formats, thumbnails and video stills (as local file paths)
    reach.md      reach per ad, audience, chosen locations, country split
    testing.md    launch pace, formats, buttons, destinations, what changed

Data labels are in English whatever the language of the instructions.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import consumption, copy_analysis
from .report import slugify
from .storage import home_dir

SLICES = ("overview", "copy", "creative", "reach", "testing")


def _pct(share) -> str:
    return f"{round((share or 0) * 100)}%"


def _n(value) -> str:
    return f"{value:,}" if isinstance(value, (int, float)) else "n/a"


def _counts(counter: dict) -> str:
    return ", ".join(f"{key} ({count})" for key, count in counter.items()) or "none"


def _top(rows: list[dict], key: str, limit: int = 6) -> str:
    return ", ".join(f"{row[key]} {_pct(row['share'])}" for row in rows[:limit]) or "none"


def _quote(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + " [...]"
    return "\n".join("> " + line for line in text.splitlines()) or "> (no text)"


def subject_name(result: dict) -> str:
    return (result.get("page") or {}).get("name") or result.get("query") or "search"


def _head(rank: int, ad: dict) -> str:
    return (f"### {rank}. {ad.get('advertiser') or 'Unknown'} · id {ad['library_id']}\n"
            f"score {ad['longevity_score']} ({ad.get('tier')}) · {ad.get('days_running')} days · "
            f"copy used in {ad.get('repetitions', 1)} ads · {ad.get('media_type') or 'unknown format'}")


def overview(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    page = result.get("page") or {}
    read = sum(1 for ad in ads if (ad.get("reach") or {}).get("available"))
    lines = [f"# {subject_name(result)} · {result.get('country') or ''}".rstrip(" ·"), ""]
    if result.get("mode") == "company":
        lines.append(f"- Subject: advertiser page, category {page.get('category') or 'n/a'}, "
                     f"{_n(page.get('followers'))} followers")
    else:
        lines.append(f"- Subject: keyword search \"{result.get('query')}\" (ads from many advertisers)")
    lines += [
        f"- Collected: {result.get('fetched_at') or 'n/a'}; {result.get('ads_parsed')} ads loaded of "
        f"{_n(found.get('active_ads'))} active; {result.get('distinct_ads')} distinct texts",
        f"- In this pack: the top {len(ads)} ads by longevity score",
        "- Longevity score, 0-100: 60 points from days running (full at 90 days) plus 40 from how many "
        "ads reuse the same text (full at 10). Strong from 70, good 40-69, testing below 40. An ad whose "
        "text is used once cannot pass 60.",
        f"- Reach: read for {read} of these ads. Meta publishes it only for ads delivered in the EU or the "
        "UK, per ad. Ads sharing one text are listed once; their reach is that of one ad of the group.",
        "- Meta publishes no spend and no sales. Longevity is a clue that an ad pays, not proof.",
        "- The list on Meta is ordered by total impressions, highest first.",
    ]
    return "\n".join(lines) + "\n"


def copy(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    patterns = found["copy_patterns"]
    lines = ["# Copy", "", f"## Patterns across {patterns['texts_analyzed']} distinct texts",
             f"- Hook types (rule-based): {_counts(patterns['hook_types'])}",
             f"- Most common structures: {_counts(patterns['common_structures'])}",
             f"- Texts with proof: {_pct(patterns['share_with_proof'])}; with urgency: "
             f"{_pct(patterns['share_with_urgency'])}; naming an offer: {_pct(patterns['share_mentioning_offer'])}; "
             f"naming a price: {_pct(patterns['share_mentioning_price'])}",
             "- Most reused texts: " + ("; ".join(f"\"{row['opening']}\" (in {row['ads']} ads, id {row['library_id']})"
                                                   for row in patterns["reused_texts"]) or "none"),
             "- Openers that repeat: " + (", ".join(f"\"{row['opener']}\" ({row['texts']} texts)"
                                                    for row in patterns["repeated_openers"]) or "none"),
             f"- Languages: {_top(found['languages'], 'language')}", "",
             f"## Top {len(ads)} ads",
             "Hook, promise and proof below are a first pass made by rules. Correct them from the text."]
    for rank, ad in enumerate(ads, start=1):
        parts = copy_analysis.analyze_ad(ad)
        hook = f"hook ({parts['hook']['type']}): \"{parts['hook']['text'][:160]}\"" if parts["hook"] else "no hook found"
        promise = f"promise: \"{parts['promise']['text'][:160]}\"" if parts["promise"] else "promise: none found"
        proof = "; ".join(f"\"{p['text'][:120]}\" ({', '.join(p['kinds'])})" for p in parts["proof"]) or "none found"
        lines += ["", _head(rank, ad),
                  f"button \"{ad.get('cta') or 'none'}\" -> {ad.get('landing_domain') or 'no destination'}"
                  + (f" · headline: {ad['headline']}" if ad.get("headline") else ""),
                  f"first pass: {hook}; {promise}; proof: {proof}",
                  _quote(ad.get("body"))]
    return "\n".join(lines) + "\n"


def creative(result: dict, ads: list[dict], frames: bool) -> tuple[str, list[str]]:
    """The creative slice and the picture files it points to."""
    found = result["signals"]
    chosen = ads[:consumption.ADS_WITH_FRAMES]
    images: list[str] = []
    with_stills = sum(1 for ad in chosen if ad.get("frames")) if frames else 0
    lines = ["# Creative", "",
             "- Format mix of all active ads: " + (", ".join(f"{name} {_pct(share)}"
                                                             for name, share in found["format_share"].items()) or "n/a"),
             (f"- Video stills (start, middle, end): saved for {with_stills} of the {len(chosen)} ads below"
              if frames else "- Video stills: not collected for this pack. Work from thumbnails, formats and copy, and say so."),
             "- Pictures are local files: open them to look at the creative.", ""]
    for rank, ad in enumerate(chosen, start=1):
        reach = f" · reach per day {_n(ad.get('reach_per_day'))}" if ad.get("reach_per_day") is not None else ""
        lines += [_head(rank, ad) + reach,
                  f"opening line: \"{(ad.get('body') or '').strip().splitlines()[0][:160] if (ad.get('body') or '').strip() else ''}\""]
        stills = (ad.get("frames") or []) if frames else []
        if ad.get("thumbnail_path"):
            lines.append(f"thumbnail: {ad['thumbnail_path']}")
        if stills:
            lines.append("stills (start, middle, end): " + ", ".join(stills))
            images += stills
        else:
            if ad.get("media_type") == "video":
                lines.append("stills: none saved")
            if frames and ad.get("thumbnail_path"):
                images.append(ad["thumbnail_path"])      # the thumbnail stands in for missing stills
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", images


def reach(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    country = result.get("country") or "country"
    lines = ["# Reach and audience", "",
             "Reach is published by Meta only for ads delivered in the EU or the UK. Locations are what the "
             "advertiser targeted and can name areas outside those regions.", "",
             f"| # | id | days | EU reach | {country} reach | UK reach | per day | age | gender | breadth | locations in / out |",
             "|---:|---|---:|---:|---:|---:|---:|---|---|---|---|"]
    for rank, ad in enumerate(ads, start=1):
        data, audience = ad.get("reach"), ad.get("audience") or {}
        if data is None:
            numbers = "not read | | | "
        elif not data.get("available"):
            numbers = "not published | | | "
        else:
            numbers = (f"{_n(data.get('eu_total'))} | {_n(data.get('country_reach'))} | "
                       f"{_n(data.get('uk_total'))} | {_n(ad.get('reach_per_day'))}")
        age = f"{audience.get('age_min')}-{audience.get('age_max')}" if audience else ""
        breadth = (ad.get("audience_breadth") or {}).get("label", "")
        places = (f"{len(audience.get('locations_included', []))} / {len(audience.get('locations_excluded', []))}"
                  if audience else "")
        flag = " (flagged for review)" if ad.get("needs_review") else ""
        lines.append(f"| {rank} | {ad['library_id']}{flag} | {ad.get('days_running')} | {numbers} | {age} "
                     f"| {audience.get('gender') or ''} | {breadth} | {places} |")
    total, audience = found["reach"], found.get("audience")
    lines.append("")
    if total.get("available"):
        lines += [f"## Totals over the {total['ads_with_reach']} ads with reach",
                  f"- EU {_n(total['eu_reach_summed'])}; {total.get('country') or country} "
                  f"{_n(total.get('country_reach_summed'))}; UK {_n(total['uk_reach_summed'])} "
                  "(sums over ads: one person can be counted in several)",
                  f"- Median reach per day: {_n(total['median_reach_per_day'])}; highest: {_n(total['highest_reach_per_day'])}",
                  "- Countries by summed reach: " + ", ".join(f"{row['country']} {_n(row['reach'])}"
                                                               for row in total["top_countries"])]
    else:
        lines.append(f"## Reach\n- {total['note']}")
    if audience:
        places = lambda rows: ", ".join(  # noqa: E731
            f"{row['name']}" + (f" [{row['type']}]" if row.get("type") not in (None, "countries") else "")
            + f" ({row['ads']})" for row in rows[:20]) or "none"
        lines += ["", f"## Audience over the {audience['ads_with_audience']} ads read",
                  "- Age ranges: " + ", ".join(f"{row['age_min']}-{row['age_max']} ({row['ads']})"
                                               for row in audience["age_ranges"]),
                  f"- Gender: {_counts(audience['genders'])}; breadth: {_counts(audience['breadth'])}",
                  f"- Locations targeted (ads): {places(audience['locations_included'])}",
                  f"- Locations excluded (ads): {places(audience['locations_excluded'])}"]
    return "\n".join(lines) + "\n"


def testing(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    weeks = ", ".join(f"{week['week_start'][5:]}: {week['ads']}" for week in found["weekly_launches"])
    lines = ["# Testing and destinations", "",
             f"- Active ads: {_n(found['active_ads'])}; loaded here: {found['ads_loaded']}",
             f"- New ads per week (last four weeks): {found['new_per_week']}; started in the last 30 days: "
             f"{found['started_last_30_days']} ({_pct(found['share_started_last_30_days'])} of loaded)",
             f"- Launches per week, oldest to newest (week start: ads): {weeks}",
             f"- Score tiers of the distinct texts: {_counts(found['tiers'])}; flagged for review: {found['needs_review']}",
             f"- Platforms: {_top(found['platforms'], 'platform')}",
             f"- Buttons: {_top(found['buttons'], 'button')}",
             f"- Destinations: {_top(found['destinations'], 'domain')}"]
    changes = result.get("changes") or {}
    if changes.get("available"):
        counts = changes["counts"]
        lines.append(f"- Since the previous search ({changes['previous_taken_at']}): {counts['new']} new ads "
                     f"({counts['new_texts']} with new copy), {counts['stopped']} stopped, {counts['changed']} changed")
    else:
        lines.append("- Changes since a previous search: none recorded yet (this is the first saved search)")
    lines += ["", f"## Top {len(ads)} ads", "| # | id | started | days | copy used | format | button | destination |",
              "|---:|---|---|---:|---:|---|---|---|"]
    for rank, ad in enumerate(ads, start=1):
        lines.append(f"| {rank} | {ad['library_id']} | {ad.get('started') or ''} | {ad.get('days_running')} "
                     f"| {ad.get('repetitions', 1)} | {ad.get('media_type') or ''} | {ad.get('cta') or ''} "
                     f"| {ad.get('landing_domain') or ''} |")
    return "\n".join(lines) + "\n"


def sections(result: dict, ads: int = 10, frames: bool = False) -> tuple[dict[str, str], list[str]]:
    """The five slices for the top ``ads`` of a result, and the picture files they mention."""
    chosen = result["ads"][:max(1, int(ads))]
    creative_text, images = creative(result, chosen, frames)
    return ({"overview": overview(result, chosen), "copy": copy(result, chosen), "creative": creative_text,
             "reach": reach(result, chosen), "testing": testing(result, chosen)}, images)


def write(result: dict, level: str, slices: dict[str, str], images: list[str], brief: str,
          extra: dict[str, str] | None = None, directory: Path | None = None,
          today: date | None = None, ads: int = 0) -> dict:
    """Save a pack to its own folder and return where everything is."""
    stamp = (today or date.today()).isoformat()
    name = slugify(f"{subject_name(result)} {result.get('country') or ''} {level} {stamp}")
    folder = (Path(directory) if directory else home_dir() / "packs") / name
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, text in {**slices, **(extra or {}), "brief": brief}.items():
        path = folder / f"{key}.md"
        path.write_text(text, encoding="utf-8")
        files[key] = str(path)
    manifest = {"level": level, "subject": subject_name(result), "country": result.get("country"),
                "ads": ads,
                "files": files, "images": images, "created": stamp}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"folder": str(folder), "files": files, "images": images}
