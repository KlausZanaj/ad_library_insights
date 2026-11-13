"""Read ads from the structured data the Ad Library page itself receives.

The page gets its results as JSON twice over: the first batch sits in a script tag
of the HTML, the following ones arrive as responses while the list scrolls. Both
carry the same "search_results_connection" object, which is far steadier than the
text on screen and adds what the cards only show as icons: platforms, media
addresses, the advertiser's page id.

Each edge of the connection is one card. When several ads share creative and text
the edge lists them all; the first one carries the group counter and stands for the
card, exactly as the page shows it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

AD_URL = "https://www.facebook.com/ads/library/?id={}"
CONNECTION_KEY = "search_results_connection"

# how the library names a creative -> the media types used everywhere else
_FORMATS = {"video": "video", "image": "image", "carousel": "carousel", "multi_images": "carousel",
            "multi_videos": "video", "multi_medias": "carousel", "text": "text", "event": "image"}


def find_key(obj, key: str):
    """First value stored under ``key`` anywhere inside nested dicts and lists."""
    stack = [obj]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if key in current:
                return current[key]
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return None


def load_payload(text: str):
    """Parse a response body; streamed bodies hold one JSON document per line."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    for line in (text or "").splitlines():
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def connection_from_text(text: str) -> dict | None:
    """The results connection inside a script tag or a response body, if any."""
    if not text or CONNECTION_KEY not in text:
        return None
    found = find_key(load_payload(text), CONNECTION_KEY)
    return found if isinstance(found, dict) else None


def _iso_day(stamp) -> str | None:
    if not stamp:
        return None
    return datetime.fromtimestamp(int(stamp), timezone.utc).date().isoformat()


def _domain(url: str | None) -> str | None:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def _is_template(value) -> bool:
    return isinstance(value, str) and "{{" in value


def _pick(snapshot: dict, cards: list[dict], key: str):
    """A snapshot field, or the first variation's when the snapshot holds a placeholder."""
    value = snapshot.get(key)
    if isinstance(value, dict):          # body arrives as {"text": ...}
        value = value.get("text")
    if value and not _is_template(value):
        return value
    for card in cards:
        candidate = card.get(key)
        if candidate and not _is_template(candidate):
            return candidate
    return None


def _media(snapshot: dict, cards: list[dict]) -> tuple[str, str | None, str | None]:
    """(media type, thumbnail address, video address) for a creative."""
    videos = snapshot.get("videos") or [c for c in cards if c.get("video_sd_url") or c.get("video_hd_url")]
    images = snapshot.get("images") or [c for c in cards if c.get("resized_image_url") or c.get("original_image_url")]
    thumbnail = video_url = None
    if videos:
        first = videos[0]
        thumbnail = first.get("video_preview_image_url")
        video_url = first.get("video_sd_url") or first.get("video_hd_url")
    if not thumbnail and images:
        thumbnail = images[0].get("resized_image_url") or images[0].get("original_image_url")

    raw = (snapshot.get("display_format") or "").lower()
    if raw in _FORMATS:
        kind = _FORMATS[raw]
    elif videos:                           # dynamic and catalogue creatives: judge by content
        kind = "video"
    elif len(cards) > 1 and raw != "dco":
        kind = "carousel"
    else:
        kind = "image" if images else "text"
    return kind, thumbnail, video_url


def ad_from_record(record: dict, members: list[dict] | None = None, rank: int | None = None) -> dict | None:
    """One ad in the same shape the card parser produces, plus the structured extras."""
    library_id = str(record.get("ad_archive_id") or "")
    if not library_id:
        return None
    snapshot = record.get("snapshot") or {}
    cards = snapshot.get("cards") or []
    kind, thumbnail, video_url = _media(snapshot, cards)
    raw_format = (snapshot.get("display_format") or "").lower()
    landing_url = _pick(snapshot, cards, "link_url")
    active = record.get("is_active")
    return {
        "library_id": library_id,
        "ad_url": AD_URL.format(library_id),
        "status": None if active is None else "active" if active else "inactive",
        "started": _iso_day(record.get("start_date")),
        "ended": None if active else _iso_day(record.get("end_date")),
        "copies": int(record.get("collation_count") or 1),
        "multiple_versions": raw_format in ("dco", "dpa"),
        "advertiser": snapshot.get("page_name") or record.get("page_name"),
        "advertiser_url": snapshot.get("page_profile_uri"),
        "body": _pick(snapshot, cards, "body") or "",
        "headline": _pick(snapshot, cards, "title"),
        "description": _pick(snapshot, cards, "link_description"),
        "cta": _pick(snapshot, cards, "cta_text"),
        "landing_url": landing_url,
        "landing_domain": _domain(landing_url) or (snapshot.get("caption") or "").lower() or None,
        "media_type": kind,
        "image_url": thumbnail,
        # structured extras
        "format": raw_format or None,
        "video_url": video_url,
        "logo_url": snapshot.get("page_profile_picture_url"),
        "page_id": str(record.get("page_id") or snapshot.get("page_id") or "") or None,
        "page_likes": snapshot.get("page_like_count"),
        "page_categories": snapshot.get("page_categories") or [],
        "platforms": [p.lower() for p in record.get("publisher_platform") or []],
        "collation_ids": [str(m.get("ad_archive_id")) for m in (members or [])
                          if m.get("ad_archive_id")],
        "impression_rank": rank,
    }


def ads_from_edges(edges: list[dict]) -> list[dict]:
    """Ads for every card, in page order, without the repeats that scrolling can produce.

    The page lists results by total impressions, highest first, so the position of a
    card is kept as ``impression_rank``.
    """
    ads, seen = [], set()
    for edge in edges or []:
        group = (edge.get("node") or {}).get("collated_results") or []
        if not group:
            continue
        head = next((r for r in group if r.get("collation_count")), group[0])
        ad = ad_from_record(head, [r for r in group if r is not head], rank=len(ads) + 1)
        if ad and ad["library_id"] not in seen:
            seen.update([ad["library_id"], *ad["collation_ids"]])
            ads.append(ad)
    return ads


def pages_from_typeahead(payload) -> list[dict]:
    """Advertiser pages the library's own search box suggests for a name."""
    results = find_key(payload, "page_results") or []
    pages = []
    for row in results:
        page_id = str(row.get("page_id") or row.get("id") or "")
        if not page_id:
            continue
        pages.append({
            "page_id": page_id,
            "name": row.get("name"),
            "category": row.get("category"),
            "followers": row.get("likes"),
            "page_alias": row.get("page_alias") or None,
            "instagram": row.get("ig_username") or None,
            "instagram_followers": row.get("ig_followers"),
            "verified": row.get("verification") in ("BLUE_VERIFIED", "VERIFIED"),
            "logo_url": row.get("image_uri"),
        })
    return pages
