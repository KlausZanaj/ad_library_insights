"""Turn raw card snapshots (text, links, media) into normalised ad records.

A card's visible text follows a stable order:

    Active | Inactive
    Library ID: <digits>
    Started running on <Mon D, YYYY>      (or "<date> - <date>" when inactive)
    Platforms
    [This ad has multiple versions]
    [<N> ads use this creative and text]
    [EU transparency]
    See ad details | See summary details
    <advertiser>
    Sponsored
    <body copy, one or more lines>
    <DISPLAY.DOMAIN>                      \
    <headline>                             } text of the link preview anchor
    [<description>]                        }
    <call-to-action button>               /

The link preview is identified through the card's anchors rather than by guessing
from the text, which keeps the body/headline/CTA split language-independent.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

AD_URL = "https://www.facebook.com/ads/library/?id={}"

_DATE = r"([A-Z][a-z]{2} \d{1,2}, \d{4})"
_LIBRARY_ID = re.compile(r"Library ID:\s*(\d+)")
_STARTED = re.compile(r"Started running on " + _DATE)
_DATE_RANGE = re.compile(_DATE + r"\s*[-–]\s*" + _DATE)
_COPIES = re.compile(r"(\d+) ads? use this creative and text")
_DETAILS = re.compile(r"^See (?:ad|summary) details$")
_VIDEO_TIMER = re.compile(r"^\d+:\d{2}\s*/\s*\d+:\d{2}$")
_DISPLAY_DOMAIN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*\.[A-Z]{2,}$")
_RESULTS = re.compile(r"(~?\s?[\d.,]+\s?[KM]?\+?)\s+results?\b")
_NO_RESULTS = re.compile(r"(?<![\d.,~])0 results\b|No ads match", re.IGNORECASE)


def clean_lines(text: str) -> list[str]:
    """Split into lines, dropping zero-width filler and blanks."""
    lines = (line.replace("​", "").replace("﻿", "").strip()
             for line in (text or "").splitlines())
    return [line for line in lines if line]


def _iso(label: str | None) -> str | None:
    if not label:
        return None
    try:
        return datetime.strptime(label, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def unwrap_redirect(href: str) -> str:
    """Return the real destination behind an l.facebook.com/l.php?u=... redirect."""
    parsed = urlparse(href)
    if parsed.netloc.endswith("l.facebook.com"):
        target = parse_qs(parsed.query).get("u")
        if target:
            return target[0]
    return href


def _domain(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def _find_block(lines: list[str], block: list[str]) -> int | None:
    """Index where ``block`` appears as consecutive lines, or None."""
    for i in range(len(lines) - len(block) + 1):
        if lines[i:i + len(block)] == block:
            return i
    return None


def parse_card(card: dict) -> dict | None:
    """Build one ad record from a card snapshot. Returns None if it is not an ad card."""
    lines = clean_lines(card.get("text", ""))
    id_match = _LIBRARY_ID.search("\n".join(lines))
    if not id_match:
        return None
    library_id = id_match.group(1)

    split = next((i for i, line in enumerate(lines) if _DETAILS.match(line)), None)
    header, rest = (lines[:split], lines[split + 1:]) if split is not None else (lines, [])
    header_text = "\n".join(header)

    started = _STARTED.search(header_text)
    date_range = _DATE_RANGE.search(header_text)
    copies = _COPIES.search(header_text)

    advertiser = rest[0] if rest and rest[0] != "Sponsored" else None
    content = rest[rest.index("Sponsored") + 1:] if "Sponsored" in rest else rest[1:]
    content = [line for line in content if not _VIDEO_TIMER.match(line)]

    advertiser_url = None
    previews: list[tuple[str, list[str]]] = []
    for link in card.get("links", []):
        href = link.get("href", "")
        link_lines = [l for l in clean_lines(link.get("text", "")) if not _VIDEO_TIMER.match(l)]
        host = urlparse(href).netloc.lower()
        if advertiser_url is None and host in ("www.facebook.com", "facebook.com") \
                and link_lines == [advertiser]:
            advertiser_url = href
        elif len(link_lines) >= 2:
            previews.append((href, link_lines))

    body_lines, headline, description, cta, landing_url = content, None, None, None, None
    if previews:
        href, block = previews[0]
        landing_url = unwrap_redirect(href)
        at = _find_block(content, block)
        if at is not None:
            body_lines = content[:at]
        if _DISPLAY_DOMAIN.match(block[0]):
            block = block[1:]
        if block:
            cta, middle = block[-1], block[:-1]
            headline = middle[0] if middle else None
            description = " ".join(middle[1:]) or None

    images = card.get("images", [])
    videos = [v for v in card.get("videos", []) if v]
    if card.get("videos"):
        media_type = "video"
    elif len(previews) > 1:
        media_type = "carousel"
    else:
        media_type = "image" if len(images) > 1 else "text"

    return {
        "library_id": library_id,
        "ad_url": AD_URL.format(library_id),
        "status": header[0].lower() if header and header[0] in ("Active", "Inactive") else None,
        "started": _iso(started.group(1) if started else date_range.group(1) if date_range else None),
        "ended": _iso(date_range.group(2)) if date_range else None,
        "copies": int(copies.group(1)) if copies else 1,
        "multiple_versions": "This ad has multiple versions" in header,
        "advertiser": advertiser,
        "advertiser_url": advertiser_url,
        "body": "\n".join(body_lines),
        "headline": headline,
        "description": description,
        "cta": cta,
        "landing_url": landing_url,
        "landing_domain": _domain(landing_url) if landing_url else None,
        "media_type": media_type,
        # the first image of a card is the advertiser avatar
        "image_url": videos[0] if videos else images[-1] if len(images) > 1 else None,
    }


def parse_cards(cards: list[dict]) -> list[dict]:
    """Parse every card, skipping non-ads and cards re-rendered by infinite scroll."""
    ads, seen = [], set()
    for card in cards:
        ad = parse_card(card)
        if ad and ad["library_id"] not in seen:
            seen.add(ad["library_id"])
            ads.append(ad)
    return ads


def results_label(page_text: str) -> str | None:
    """The page's own result counter, e.g. "~300 results"."""
    match = _RESULTS.search(page_text or "")
    return f"{match.group(1).replace(' ', '')} results" if match else None


def says_no_results(page_text: str) -> bool:
    """True when the page itself states the search matched nothing."""
    return bool(_NO_RESULTS.search(page_text or ""))
