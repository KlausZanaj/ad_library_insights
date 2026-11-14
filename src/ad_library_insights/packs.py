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
    extra = []
    if ad.get("kind") not in (None, "standard"):
        extra.append("catalogue ad" if ad["kind"] == "catalog" else "dynamic ad with versions")
    if len(ad.get("languages") or []) > 1:
        extra.append(f"translated: {', '.join(ad['languages'])}")
    if ad.get("copies_total", 1) > ad.get("cards", 1):
        extra.append(f"{ad['copies_total']} identical copies in all")
    return (f"### {rank}. {ad.get('advertiser') or 'Unknown'} · id {ad['library_id']}\n"
            f"rating {ad['score']} ({ad.get('verdict')}, reliability {ad.get('reliability')}) · "
            f"{ad.get('days_running')} days · {ad.get('creatives', 1)} creatives in {ad.get('cards', 1)} ads · "
            f"{ad.get('media_type') or 'unknown format'}" + (" · " + "; ".join(extra) if extra else ""))


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
        f"- In this pack: the top {len(ads)} ads by rating",
        f"- Rating, 0-100, three parts: scale (people reached per day in {result.get('country') or 'the country searched'}; "
        "where that is not published, the position by impressions), staying power (days running, full at 90) "
        "and creative investment (different creatives for one concept). Scale and creatives are relative to "
        "the other ads here.",
        "- Reach per day = people reached in the country searched, divided by the days the ad has been on "
        "air (seven at the least). The EU and UK totals are information and do not rate.",
        "- Reach counts unique people, who grow slower than days: an ad on air for months shows fewer people "
        "per day than it had at the start. Read the total reached next to the daily figure.",
        "- Reliability of a rating: high = reach in the country searched was read; medium = impression "
        "position only; low = neither.",
        "- Verdicts: scaling (reaches many people per day compared with the others), holding (90 days or "
        "more with scale in the middle or above), testing (under 30 days; under 7 days an ad is too recent "
        "to judge), review (90 days or more with low scale: a small budget that works or a forgotten ad, "
        "to be checked, not a negative verdict), average (the rest).",
        "- One ad per concept: identical copies, versions of a dynamic ad, catalogue ads and translations "
        "are merged and do not count as creatives.",
        f"- Reach: read for {read} of these ads. Meta publishes it only for ads delivered in the EU or the "
        "UK, per ad. Ads sharing one text are listed once; their reach is that of one ad of the group.",
        "- Meta publishes no spend and no sales. Scale and staying power are clues that an ad pays, not proof.",
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
             "- Concepts with most creatives: " + ("; ".join(f"\"{row['opening']}\" ({row['creatives']} creatives, id {row['library_id']})"
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
        reach = (f" · {_n(ad.get('reach_total'))} people reached in {result.get('country') or 'the country searched'}, "
                 f"{_n(ad.get('reach_per_day'))} per day" if ad.get("reach_per_day") is not None else "")
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
             f"Per day = reach in {country} divided by the days the ad has been on air, seven at the least. "
             "Reach counts unique people: over months it grows slower than days, so compare totals too.", "",
             f"| # | id | days | {country} reach | per day in {country} | EU reach | UK reach | age | gender | breadth | locations in / out |",
             "|---:|---|---:|---:|---:|---:|---:|---|---|---|---|"]
    for rank, ad in enumerate(ads, start=1):
        data, audience = ad.get("reach"), ad.get("audience") or {}
        if data is None:
            numbers = "not read | | | "
        elif not data.get("available"):
            numbers = "not published | | | "
        else:
            numbers = (f"{_n(data.get('country_reach'))} | {_n(ad.get('reach_per_day'))} | "
                       f"{_n(data.get('eu_total'))} | {_n(data.get('uk_total'))}")
        age = f"{audience.get('age_min')}-{audience.get('age_max')}" if audience else ""
        breadth = (ad.get("audience_breadth") or {}).get("label", "")
        places = (f"{len(audience.get('locations_included', []))} / {len(audience.get('locations_excluded', []))}"
                  if audience else "")
        flag = (" (flagged for review)" if ad.get("needs_review")
                else " (too recent to judge)" if ad.get("too_recent") else "")
        lines.append(f"| {rank} | {ad['library_id']}{flag} | {ad.get('days_running')} | {numbers} | {age} "
                     f"| {audience.get('gender') or ''} | {breadth} | {places} |")
    total, audience = found["reach"], found.get("audience")
    lines.append("")
    if total.get("available"):
        lines += [f"## Across the {total['ads_with_reach']} ads with published reach",
                  "- Figures are unique people per ad. They are not added up: one person can see several ads.",
                  f"- Per ad, in {total.get('country') or country} ({total.get('ads_with_market_reach', 0)} ads): median "
                  f"{_n(total['median_reach_per_day'])} people per day ({_n(total.get('median_reach_total'))} in total), "
                  f"best {_n(total['highest_reach_per_day'])} per day ({_n(total.get('highest_reach_total'))} in total)",
                  "- Where delivery goes (share of the reach of these ads, by country; the same person can "
                  "count in several ads): " + ", ".join(
                      f"{row['country']} {_pct(row.get('share'))}" for row in total["top_countries"])]
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
             f"- Verdicts of the ads: {_counts(found['verdicts'])}; flagged for review: {found['needs_review']}",
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
    lines += ["", f"## Top {len(ads)} ads", "| # | id | started | days | creatives | format | button | destination |",
              "|---:|---|---|---:|---:|---|---|---|"]
    for rank, ad in enumerate(ads, start=1):
        lines.append(f"| {rank} | {ad['library_id']} | {ad.get('started') or ''} | {ad.get('days_running')} "
                     f"| {ad.get('creatives', 1)} | {ad.get('media_type') or ''} | {ad.get('cta') or ''} "
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
