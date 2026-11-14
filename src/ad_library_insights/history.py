"""Remember each search and tell what changed since the previous one.

The Ad Library shows what runs today, not what started or stopped. Every search is
therefore saved as a small snapshot in the tool's home folder; comparing the last
two snapshots of the same company or keyword gives new ads, ads no longer listed,
and ads whose copy or offer changed. It needs two searches, so the first one only
sets the baseline.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .scoring import text_fingerprint
from .storage import _read_json, _write_json, home_dir

KEEP = 30                      # snapshots kept per company or keyword
_OFFER = re.compile(r"\d+\s?%|[€$£]\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?(?:€|\$|£|eur|usd)", re.I)
_FIELDS = (("headline", "headline"), ("cta", "button"), ("landing_domain", "destination"))


def subject(result: dict) -> dict:
    """What a result is about, with a key that is the same at every search."""
    country = result.get("country") or ""
    if result.get("mode") == "company":
        page = result.get("page") or {}
        return {"key": f"company:{country}:{page.get('page_id')}", "mode": "company",
                "label": page.get("name") or result.get("query"), "country": country,
                "page_id": page.get("page_id")}
    query = result.get("query") or ""
    return {"key": f"keyword:{country}:{query.casefold()}", "mode": "keyword", "label": query,
            "country": country, "query": query}


def _lite(ad: dict) -> dict:
    """The few fields of an ad needed to compare it later and to show it in a list."""
    body = ad.get("body") or ""
    return {
        "library_id": ad["library_id"],
        "ids": sorted({ad["library_id"], *ad.get("variant_ids", []), *ad.get("collation_ids", [])}),
        "ad_url": ad.get("ad_url"),
        "advertiser": ad.get("advertiser"),
        "opening": (body.strip().splitlines() or [ad.get("headline") or ""])[0][:160],
        "body": body,
        "headline": ad.get("headline"),
        "cta": ad.get("cta"),
        "landing_domain": ad.get("landing_domain"),
        "media_type": ad.get("media_type"),
        # dynamic and catalogue ads show a different variation at every load
        "dynamic": bool(ad.get("multiple_versions")),
        "started": ad.get("started"),
        "days_running": ad.get("days_running"),
        "creatives": ad.get("creatives", 1),
        "score": ad.get("score"),
        "verdict": ad.get("verdict"),
        "thumbnail_path": ad.get("thumbnail_path"),
    }


def snapshot_of(result: dict, now: datetime | None = None) -> dict:
    taken = result.get("fetched_at") or (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    found = result.get("signals") or {}
    return {"subject": subject(result), "taken_at": taken,
            "active_ads": found.get("active_ads"), "ads_loaded": result.get("ads_parsed"),
            "ads": [_lite(ad) for ad in result.get("ads", [])]}


def _offers(ad: dict) -> set[str]:
    text = f"{ad.get('body') or ''} {ad.get('headline') or ''}"
    return {re.sub(r"\s+", "", match.lower()) for match in _OFFER.findall(text)}


def _public(ad: dict) -> dict:
    return {key: value for key, value in ad.items() if key not in ("body", "ids")}


def compare(previous: dict, current: dict) -> dict:
    """New, stopped and changed ads between two snapshots of the same subject.

    Ads are matched by library id, counting the ids of ads merged for sharing one
    text, so a group is "stopped" only when none of its ads is listed any more.
    "Changed" means the same ad now shows different copy, headline, button,
    destination, or different prices and percentages (its offer). Dynamic ads are
    left out of it: they rotate their variations by design.
    """
    before = {i: ad for ad in previous["ads"] for i in ad["ids"]}
    after = {i: ad for ad in current["ads"] for i in ad["ids"]}
    known_texts = {(ad.get("advertiser"), text_fingerprint(ad.get("body") or "")) for ad in previous["ads"]}

    new, changed = [], []
    for ad in current["ads"]:
        old = next((before[i] for i in ad["ids"] if i in before), None)
        if old is None:
            fresh_text = (ad.get("advertiser"), text_fingerprint(ad.get("body") or "")) not in known_texts
            new.append({**_public(ad), "new_text": fresh_text})
            continue
        if old.get("dynamic") or ad.get("dynamic"):
            continue                      # a rotating variation is not an edit
        fields = []
        if text_fingerprint(old.get("body") or "") != text_fingerprint(ad.get("body") or ""):
            fields.append("text")
        fields += [name for key, name in _FIELDS if (old.get(key) or "") != (ad.get(key) or "")]
        if _offers(old) != _offers(ad):
            fields.append("offer")
        if fields:
            changed.append({**_public(ad), "fields": fields,
                            "before": {"opening": old.get("opening"), "headline": old.get("headline"),
                                       "cta": old.get("cta"), "landing_domain": old.get("landing_domain")}})
    stopped = [_public(ad) for ad in previous["ads"] if not any(i in after for i in ad["ids"])]
    new.sort(key=lambda ad: ad.get("started") or "", reverse=True)      # latest launches first

    then = datetime.fromisoformat(previous["taken_at"])
    now = datetime.fromisoformat(current["taken_at"])
    return {
        "available": True,
        "subject": current["subject"],
        "previous": {k: previous.get(k) for k in ("taken_at", "active_ads", "ads_loaded")},
        "current": {k: current.get(k) for k in ("taken_at", "active_ads", "ads_loaded")},
        "days_between": round((now - then).total_seconds() / 86400, 1),
        # a keyword search loads the most shown ads, not all of them
        "sample": current["subject"]["mode"] == "keyword",
        "counts": {"new": len(new), "new_texts": sum(ad["new_text"] for ad in new),
                   "stopped": len(stopped), "changed": len(changed)},
        "new": new, "stopped": stopped, "changed": changed,
    }


class History:
    """Snapshots on disk, one folder per company or keyword."""

    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else home_dir() / "snapshots"

    def _folder(self, key: str) -> Path:
        return self.directory / hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def snapshots(self, key: str) -> list[dict]:
        """Saved snapshots of one subject, oldest first."""
        folder = self._folder(key)
        found = [_read_json(path) for path in sorted(folder.glob("*.json"))] if folder.is_dir() else []
        return sorted((s for s in found if s and s.get("ads") is not None), key=lambda s: s["taken_at"])

    def record(self, result: dict) -> dict:
        """Save a snapshot of a search that returned ads and report what changed.

        A result served again from the cache carries the same timestamp and is not
        saved twice. Returns the output of ``changes`` for this subject.
        """
        if not result.get("ads"):
            return {"available": False, "reason": "no_ads"}
        snap = snapshot_of(result)
        key = snap["subject"]["key"]
        folder = self._folder(key)
        path = folder / (re.sub(r"[^0-9A-Za-z]", "", snap["taken_at"]) + ".json")
        if not path.exists():
            _write_json(path, snap)
            for old in sorted(folder.glob("*.json"))[:-KEEP]:
                old.unlink(missing_ok=True)
        return self.changes(key)

    def changes(self, key: str) -> dict:
        """What changed between the last two snapshots of a subject."""
        saved = self.snapshots(key)
        if len(saved) < 2:
            return {"available": False, "reason": "first_search" if saved else "never_searched",
                    "subject": saved[0]["subject"] if saved else None, "snapshots": len(saved)}
        return {**compare(saved[-2], saved[-1]), "snapshots": len(saved)}

    def subjects(self) -> list[dict]:
        """Every company or keyword searched so far, latest search first."""
        rows = []
        for folder in (self.directory.iterdir() if self.directory.is_dir() else []):
            files = sorted(folder.glob("*.json")) if folder.is_dir() else []
            last = _read_json(files[-1]) if files else None
            if not last:
                continue
            rows.append({**last["subject"], "snapshots": len(files), "last_taken_at": last["taken_at"],
                         "active_ads": last.get("active_ads")})
        return sorted(rows, key=lambda row: row["last_taken_at"], reverse=True)


def summary(changes: dict) -> dict:
    """The short form attached to a search result."""
    if not changes.get("available"):
        return {"available": False, "reason": changes.get("reason"), "key": (changes.get("subject") or {}).get("key")}
    return {"available": True, "key": changes["subject"]["key"],
            "previous_taken_at": changes["previous"]["taken_at"],
            "days_between": changes["days_between"], "counts": changes["counts"]}
