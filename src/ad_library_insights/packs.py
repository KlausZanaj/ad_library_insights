"""Turn a research result into a data pack an assistant can read: one file per specialist.

Plain code, no model. The Analysis and Plan levels hand the collected data to the
user's own assistant; to keep that cheap, the data is cut into slices, so that a
specialist looking at copy never has to read reach tables, and the other way round:

    overview.md   what was collected, how the rating works, the ad types, what the data cannot say
    copy.md       the texts of the top ads and the patterns across all texts
    creative.md   formats and the pictures to look at (file names inside ``frames/``)
    reach.md      reach per ad, audience, chosen locations, languages and countries
    testing.md    launch pace, ads on air by age, survival between searches, destinations
    frames/       the video stills (start, middle, end) and pictures the creative file names

Pictures are copied into the pack, so every file refers to them by a short name and
no text carries a path of the computer it was made on. Data labels are in English
whatever the language of the instructions.
"""
from __future__ import annotations

import json
import shutil
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from . import consumption, copy_analysis, history
from .report import slugify
from .storage import home_dir

SLICES = ("overview", "copy", "creative", "reach", "testing")
FRAMES_FOLDER = "frames"
STILL_NAMES = ("start", "middle", "end")

# The types a specialist sorts every ad into. Code can tell the first and hint at two
# others from the format; the rest needs someone to read the text or look at the picture.
AD_TYPES = (
    ("catalogue or dynamic", "a product feed or automatic versions fill the ad; nobody made this exact creative by hand"),
    ("UGC or creator", "a customer or a creator films the product or talks to the camera in their own setting"),
    ("founder talking", "someone from the company speaks in the first person about why the product exists"),
    ("product demo", "the product in use: what it does, how, and the result"),
    ("gameplay", "footage of the game or the app itself, real or staged"),
    ("static promo", "one picture carrying an offer, a price or a claim"),
    ("product carousel", "several cards, one product or one argument per card"),
)


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


def type_hint(ad: dict) -> str:
    """What the format alone says about the type of an ad. A hint to confirm, not a label."""
    if ad.get("kind") == "catalog":
        return "catalogue or dynamic (a product feed fills it)"
    if ad.get("kind") == "dynamic":
        return "catalogue or dynamic (automatic versions of one ad): say what the version shown is"
    media = ad.get("media_type")
    if media == "carousel":
        return "product carousel, to confirm"
    if media == "image":
        return "static promo, to confirm"
    if media == "video":
        return "video: UGC or creator, founder talking, product demo or gameplay, to tell from text and stills"
    return "not told by the format"


def _reached(ad: dict, country: str) -> str:
    """What is known about the scale of an ad, in words that never pass an estimate off as data."""
    if ad.get("reach_per_day") is not None:
        return f" · {_n(ad.get('reach_total'))} people reached in {country}, {_n(ad.get('reach_per_day'))} per day"
    if ad.get("reach_in_market") is False:
        return f" · reach in {country}: not published (the reach read is for the EU or the UK and does not count here)"
    if ad.get("scale_basis") == "impressions":
        return f" · reach in {country}: not known; position {ad.get('impression_rank')} by impressions"
    return f" · reach in {country}: not known"


def _head(rank: int, ad: dict) -> str:
    extra = []
    if len(ad.get("languages") or []) > 1:
        extra.append(f"translated: {', '.join(ad['languages'])}")
    if ad.get("copies_total", 1) > ad.get("cards", 1):
        extra.append(f"{ad['copies_total']} identical copies in all")
    if ad.get("too_recent"):
        extra.append("too recent to judge")
    return (f"### {rank}. {ad.get('advertiser') or 'Unknown'} · id {ad['library_id']}\n"
            f"rating {ad['score']} ({ad.get('verdict')}, reliability {ad.get('reliability')}) · "
            f"{ad.get('days_running')} days · {ad.get('creatives', 1)} creatives in {ad.get('cards', 1)} ads · "
            f"{ad.get('media_type') or 'unknown format'}" + (" · " + "; ".join(extra) if extra else "")
            + f"\ntype hint from the format: {type_hint(ad)}")


def overview(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    page = result.get("page") or {}
    country = result.get("country") or "the country searched"
    read = sum(1 for ad in ads if ad.get("reach_per_day") is not None)
    elsewhere = sum(1 for ad in ads if ad.get("reach_in_market") is False)
    lines = [f"# {subject_name(result)} · {result.get('country') or ''}".rstrip(" ·"), ""]
    if result.get("mode") == "company":
        lines.append(f"- Subject: advertiser page, category {page.get('category') or 'n/a'}, "
                     f"{_n(page.get('followers'))} followers")
    else:
        lines.append(f"- Subject: keyword search \"{result.get('query')}\" (ads from many advertisers)")
    lines += [
        f"- Collected: {result.get('fetched_at') or 'n/a'}; {result.get('ads_parsed')} ads loaded of "
        f"{_n(found.get('active_ads'))} active; {result.get('distinct_ads')} concepts after merging",
        f"- In this pack: the top {len(ads)} ads by rating",
        f"- Rating, 0-100, three parts: scale (people reached per day in {country}; "
        "where that is not published, the position by impressions), staying power (days running, full at 90) "
        "and creative investment (different creatives for one concept). Scale and creatives are relative to "
        "the other ads here.",
        f"- Reach per day = people reached in {country}, divided by the days the ad has been on "
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
        f"- Reach in {country}: read for {read} of these {len(ads)} ads. Meta publishes reach only for ads "
        "delivered in the EU or the UK, per ad. Ads sharing one text are listed once; their reach is that of "
        "one ad of the group.",
    ]
    if not read:
        lines.append(
            f"- NO REACH IN {str(country).upper()}: nothing in this pack says how many people these ads reached "
            f"there. Do not write about people reached, impressions or spend in {country} as if they were known. "
            "What is known is the order of the list (by total impressions), the dates and the creatives."
            + (f" {elsewhere} ads carry a reach figure for the EU or the UK: it describes another market." if elsewhere else ""))
    lines += [
        "- Meta publishes no spend and no sales. Scale and staying power are clues that an ad pays, not proof.",
        "- The list on Meta is ordered by total impressions, highest first.",
        "",
        "## Ad types",
        "Every ad in the copy and creative files is to be sorted into one of these. The files give a hint "
        "from the format; the type itself comes from the text and from the pictures.",
        *[f"- {name}: {meaning}" for name, meaning in AD_TYPES],
        "- other: none of the above; say what it is in three words",
    ]
    return "\n".join(lines) + "\n"


def copy(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    country = result.get("country") or "the country searched"
    patterns = found["copy_patterns"]
    lines = ["# Copy", "", f"## Patterns across {patterns['texts_analyzed']} concepts with a text",
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
        lines += ["", _head(rank, ad) + _reached(ad, country),
                  f"button \"{ad.get('cta') or 'none'}\" -> {ad.get('landing_domain') or 'no destination'}"
                  + (f" · headline: {ad['headline']}" if ad.get("headline") else ""),
                  f"first pass: {hook}; {promise}; proof: {proof}",
                  _quote(ad.get("body"))]
    return "\n".join(lines) + "\n"


def _picture(rank: int, ad: dict, label: str, source: str) -> dict:
    suffix = Path(source).suffix.lower() or ".jpg"
    return {"name": f"{FRAMES_FOLDER}/{rank:02d}-{ad['library_id']}-{label}{suffix}", "source": source}


def creative(result: dict, ads: list[dict], frames: bool) -> tuple[str, list[dict]]:
    """The creative slice and the pictures it names: ``{"name": "frames/...", "source": path}``."""
    found = result["signals"]
    country = result.get("country") or "the country searched"
    chosen = ads[:consumption.ADS_WITH_FRAMES]
    pictures: list[dict] = []
    with_stills = sum(1 for ad in chosen if ad.get("frames")) if frames else 0
    lines = ["# Creative", "",
             "- Format mix of all active ads: " + (", ".join(f"{name} {_pct(share)}"
                                                             for name, share in found["format_share"].items()) or "n/a"),
             (f"- Video stills (start, middle, end): saved for {with_stills} of the {len(chosen)} ads below. "
              f"Pictures are in the folder `{FRAMES_FOLDER}` next to this file; open them to look at the creative."
              if frames else
              "- Pictures: not collected for this pack. Work from formats and copy, and say so."), ""]
    for rank, ad in enumerate(chosen, start=1):
        opening = (ad.get("body") or "").strip().splitlines()[0][:160] if (ad.get("body") or "").strip() else ""
        lines += [_head(rank, ad) + _reached(ad, country), f"opening line: \"{opening}\""]
        if frames:
            stills = [_picture(rank, ad, label, source) for label, source in zip(STILL_NAMES, ad.get("frames") or [])]
            if stills:
                lines.append("stills (start, middle, end): " + ", ".join(still["name"] for still in stills))
                pictures += stills
            else:
                if ad.get("media_type") == "video":
                    lines.append("stills: none saved")
                if ad.get("thumbnail_path"):
                    thumbnail = _picture(rank, ad, "picture", ad["thumbnail_path"])
                    lines.append(f"picture: {thumbnail['name']}")
                    pictures.append(thumbnail)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", pictures


def _countries(data: dict, limit: int = 3) -> str:
    """The countries an ad reached most, with their share of its reach."""
    rows = sorted((row for region in data.get("regions") or [] for row in region["countries"]),
                  key=lambda row: -row["reach"])
    total = sum(row["reach"] for row in rows)
    if not rows or not total:
        return ""
    return ", ".join(f"{row['country']} {_pct(row['reach'] / total)}" for row in rows[:limit])


def reach(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    country = result.get("country") or "country"
    lines = ["# Reach and audience", "",
             "Reach is published by Meta only for ads delivered in the EU or the UK. Locations are what the "
             "advertiser targeted and can name areas outside those regions.", "",
             f"Per day = reach in {country} divided by the days the ad has been on air, seven at the least. "
             "Reach counts unique people: over months it grows slower than days, so compare totals too.", "",
             f"| # | id | days | {country} reach | per day in {country} | EU reach | UK reach | countries reached (top, share of the ad's reach) "
             "| languages of the text | age | gender | breadth | locations in / out |",
             "|---:|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|"]
    for rank, ad in enumerate(ads, start=1):
        data, audience = ad.get("reach"), ad.get("audience") or {}
        if data is None:
            numbers = "not read | | | | "
        elif not data.get("available"):
            numbers = "not published | | | | "
        else:
            split = _countries(data)
            where = f"{data.get('countries_reached') or 0}" + (f": {split}" if split else "")
            in_country = _n(data.get("country_reach")) if data.get("country_reach") is not None else "not published"
            numbers = (f"{in_country} | {_n(ad.get('reach_per_day'))} | "
                       f"{_n(data.get('eu_total'))} | {_n(data.get('uk_total'))} | {where}")
        age = f"{audience.get('age_min')}-{audience.get('age_max')}" if audience else ""
        breadth = (ad.get("audience_breadth") or {}).get("label", "")
        places = (f"{len(audience.get('locations_included', []))} / {len(audience.get('locations_excluded', []))}"
                  if audience else "")
        flag = (" (flagged for review)" if ad.get("needs_review")
                else " (too recent to judge)" if ad.get("too_recent") else "")
        lines.append(f"| {rank} | {ad['library_id']}{flag} | {ad.get('days_running')} | {numbers} "
                     f"| {', '.join(ad.get('languages') or []) or 'not recognised'} | {age} "
                     f"| {audience.get('gender') or ''} | {breadth} | {places} |")
    total, audience = found["reach"], found.get("audience")
    lines.append("")
    if total.get("available") and total.get("ads_with_market_reach"):
        lines += [f"## Across the {total['ads_with_market_reach']} ads with reach in {total.get('country') or country}",
                  "- Figures are unique people per ad. They are not added up: one person can see several ads.",
                  f"- Per ad, in {total.get('country') or country}: median "
                  f"{_n(total['median_reach_per_day'])} people per day ({_n(total.get('median_reach_total'))} in total), "
                  f"best {_n(total['highest_reach_per_day'])} per day ({_n(total.get('highest_reach_total'))} in total)"]
    elif total.get("available"):
        lines += [f"## Reach in {total.get('country') or country}: not published",
                  f"- {total['ads_with_reach']} of the ads read carry a reach figure, but it is for the EU or the UK. "
                  f"It says nothing about {total.get('country') or country}: do not use it as scale there."]
    else:
        lines.append(f"## Reach\n- {total['note']}")
    translated = [ad for ad in result["ads"] if len(ad.get("languages") or []) > 1]
    lines += ["", "## Languages and countries (for the localisation reading)",
              f"- Languages of the texts, all ads loaded: {_top(found['languages'], 'language', 10)}"
              + (f"; not recognised: {found['language_unknown']} ads" if found.get("language_unknown") else ""),
              f"- Concepts that exist in more than one language: {len(translated)} of {len(result['ads'])}"
              + ("".join(f"; id {ad['library_id']} in {', '.join(ad['languages'])} "
                         f"({ad.get('creatives', 1)} creatives for {ad.get('texts', 1)} texts)" for ad in translated[:5]))]
    if total.get("available") and total.get("top_countries"):
        lines.append("- Where delivery goes (each country's share of the reach of the ads read; the same person can "
                     "count in several ads): " + ", ".join(f"{row['country']} {_pct(row.get('share'))}"
                                                           for row in total["top_countries"]))
    else:
        lines.append("- Where delivery goes: not published for these ads")
    if audience:
        places = lambda rows: ", ".join(  # noqa: E731
            f"{row['name']}" + (f" [{row['type']}]" if row.get("type") not in (None, "countries") else "")
            + f" ({row['ads']})" for row in rows[:20]) or "none"
        lines += ["", f"## Audience over the {audience['ads_with_audience']} ads read",
                  "- Age ranges: " + ", ".join(f"{row['age_min']}-{row['age_max']} ({row['ads']})"
                                               for row in audience["age_ranges"]),
                  f"- Gender: {_counts(audience['genders'])}; breadth: {_counts(audience['breadth'])}",
                  f"- Locations targeted (ads): {places(audience['locations_included'])}"
                  + (f"; {audience['locations_included_count']} different locations in all"
                     if audience.get("locations_included_count", 0) > 20 else ""),
                  f"- Locations excluded (ads): {places(audience['locations_excluded'])}"]
    return "\n".join(lines) + "\n"


def _by_age(ads: list[dict]) -> list[str]:
    """The ads on air now, grouped by age: how many, how they are rated, how many people a day."""
    rows = ["| age of the ad | ads on air | scaling | holding | testing | review | average | median people per day (ads read) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for label, _, _ in history.AGE_GROUPS:
        group = [ad for ad in ads if history.age_group(ad.get("days_running")) == label]
        verdicts = Counter(ad.get("verdict") for ad in group)
        rates = [ad["reach_per_day"] for ad in group if ad.get("reach_per_day") is not None]
        median = f"{_n(round(statistics.median(rates)))} ({len(rates)})" if rates else "n/a"
        rows.append(f"| {label} | {len(group)} | {verdicts['scaling']} | {verdicts['holding']} | {verdicts['testing']} "
                    f"| {verdicts['review']} | {verdicts['average']} | {median} |")
    return rows


def _survival(changes: dict) -> list[str]:
    found = (changes or {}).get("survival") or {"measurable": False, "reason": "first_search"}
    if not found.get("measurable"):
        why = {"first_search": "this is the first saved search of this subject: one search shows only the ads still "
                               "on air, never the ones already stopped",
               "sample": "a keyword search loads a sample of the most shown ads, and an ad can leave the sample "
                         "without having stopped",
               "partial_list": "the list of ads was not read in full in one of the two searches"}
        return [f"- Survival: NOT MEASURABLE. Reason: {why.get(found.get('reason'), why['first_search'])}. "
                "Do not state a survival or cut rate; say it cannot be measured yet and what would make it measurable "
                "(a second search of the same company some days later)."]
    rows = [f"- Survival between the two searches ({changes.get('days_between')} days apart), by the age the ad had "
            "at the earlier one. Compare each group only with itself:",
            "", "| age at the earlier search | listed then | still listed | stopped | still listed, share |",
            "|---|---:|---:|---:|---:|"]
    for group in found["groups"]:
        share = _pct(group["still_listed"] / group["listed_before"]) if group["listed_before"] else "n/a"
        rows.append(f"| {group['age']} | {group['listed_before']} | {group['still_listed']} | {group['stopped']} | {share} |")
    return rows + [""]


def testing(result: dict, ads: list[dict]) -> str:
    found = result["signals"]
    weeks = ", ".join(f"{week['week_start'][5:]}: {week['ads']}" for week in found["weekly_launches"])
    lines = ["# Testing and destinations", "",
             f"- Active ads: {_n(found['active_ads'])}; loaded here: {found['ads_loaded']}",
             f"- New ads per week (ads still on air that started in the last four weeks, divided by four): "
             f"{found['new_per_week']}; started in the last 30 days: {found['started_last_30_days']} "
             f"({_pct(found['share_started_last_30_days'])} of loaded). Ads launched and already stopped are not "
             "in these figures, so the real launch pace is the same or higher.",
             f"- Launches per week, oldest to newest (week start: ads still on air): {weeks}",
             f"- Verdicts of the ads: {_counts(found['verdicts'])}; flagged for review: {found['needs_review']}",
             f"- Platforms: {_top(found['platforms'], 'platform')}",
             f"- Buttons: {_top(found['buttons'], 'button')}",
             f"- Destinations: {_top(found['destinations'], 'domain')}",
             "", "## Ads on air now, by age",
             "A photo of what runs today. It cannot show survival: the ads already stopped are missing from it.",
             "", *_by_age(result["ads"]),
             "", "## Survival"]
    changes = result.get("changes") or {}
    lines += _survival(changes)
    if changes.get("available"):
        counts = changes["counts"]
        lines.append(f"- Since the previous search ({changes['previous_taken_at']}): {counts['new']} new ads "
                     f"({counts['new_texts']} with new copy), {counts['stopped']} no longer listed, {counts['changed']} changed")
    lines += ["", f"## Top {len(ads)} ads", "| # | id | started | days | creatives | format | button | destination |",
              "|---:|---|---|---:|---:|---|---|---|"]
    for rank, ad in enumerate(ads, start=1):
        lines.append(f"| {rank} | {ad['library_id']} | {ad.get('started') or ''} | {ad.get('days_running')} "
                     f"| {ad.get('creatives', 1)} | {ad.get('media_type') or ''} | {ad.get('cta') or ''} "
                     f"| {ad.get('landing_domain') or ''} |")
    return "\n".join(lines) + "\n"


def sections(result: dict, ads: int = 10, frames: bool = False) -> tuple[dict[str, str], list[dict]]:
    """The five slices for the top ``ads`` of a result, and the pictures the creative slice names."""
    chosen = result["ads"][:max(1, int(ads))]
    creative_text, pictures = creative(result, chosen, frames)
    return ({"overview": overview(result, chosen), "copy": copy(result, chosen), "creative": creative_text,
             "reach": reach(result, chosen), "testing": testing(result, chosen)}, pictures)


def folder_for(result: dict, level: str, directory: Path | None = None, today: date | None = None) -> Path:
    stamp = (today or date.today()).isoformat()
    name = slugify(f"{subject_name(result)} {result.get('country') or ''} {level} {stamp}")
    return (Path(directory) if directory else home_dir() / "packs") / name


def write(result: dict, level: str, slices: dict[str, str], pictures: list[dict], brief: str,
          extra: dict[str, str] | None = None, directory: Path | None = None,
          today: date | None = None, ads: int = 0) -> dict:
    """Save a pack to its own folder and return where everything is.

    The ``frames`` folder is rebuilt every time: it holds the pictures of this analysis
    and nothing else, so it can be opened and attached as it is.
    """
    folder = folder_for(result, level, directory, today)
    frames_folder = folder / FRAMES_FOLDER
    if frames_folder.is_dir():
        shutil.rmtree(frames_folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, text in {**slices, **(extra or {}), "brief": brief}.items():
        path = folder / f"{key}.md"
        path.write_text(text, encoding="utf-8")
        files[key] = str(path)
    images = []
    for picture in pictures:
        source = Path(picture["source"])
        if source.is_file():
            frames_folder.mkdir(exist_ok=True)
            target = folder / picture["name"]
            shutil.copyfile(source, target)
            images.append(str(target))
    manifest = {"level": level, "subject": subject_name(result), "country": result.get("country"),
                "ads": ads, "files": sorted(Path(path).name for path in files.values()),
                "images": [picture["name"] for picture in pictures],
                "created": (today or date.today()).isoformat()}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"folder": str(folder), "files": files, "images": images,
            "frames_folder": str(frames_folder) if images else None}
