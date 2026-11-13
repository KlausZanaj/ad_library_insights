"""Keep thumbnails and page logos on disk.

The image addresses the Ad Library hands out are signed and expire after a while, so
a saved search would soon point at broken pictures. The files are small; they are
downloaded once, while the search is fresh, into the tool's home folder.
"""
from __future__ import annotations

import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .storage import home_dir

_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
               "image/gif": ".gif", "image/avif": ".avif"}
MAX_BYTES = 3_000_000


def _http_get(url: str, timeout: float = 20.0) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https only, checked below)
        return response.read(MAX_BYTES + 1), response.headers.get("content-type", "")


class MediaStore:
    """Downloads pictures into one folder and remembers what is already there."""

    def __init__(self, directory: Path | None = None,
                 fetcher: Callable[[str], tuple[bytes, str]] = _http_get):
        self.directory = Path(directory) if directory else home_dir() / "media"
        self._fetch = fetcher

    def existing(self, name: str) -> Path | None:
        return next(iter(sorted(self.directory.glob(name + ".*"))), None)

    def save(self, url: str | None, name: str) -> str | None:
        """Path of the picture saved under ``name``, or None if it could not be fetched."""
        if not url or not url.startswith("https://"):
            return None
        already = self.existing(name)
        if already:
            return str(already)
        try:
            data, content_type = self._fetch(url)
        except Exception:  # an expired address or a network error is not worth failing a search
            return None
        extension = _EXTENSIONS.get(content_type.split(";")[0].strip().lower())
        if not extension or not data or len(data) > MAX_BYTES:
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (name + extension)
        path.write_bytes(data)
        return str(path)

    def frame_stem(self, library_id: str) -> Path:
        return self.directory / f"ad_{library_id}_frame"

    def frames(self, library_id: str) -> list[str]:
        return [str(p) for p in sorted(self.directory.glob(f"ad_{library_id}_frame_*.jpg"))]


def save_ad_media(ads: list[dict], store: MediaStore, workers: int = 6) -> int:
    """Download thumbnail and page logo of each ad; set ``thumbnail_path`` / ``logo_path``.

    Logos are shared by all the ads of a page, so each is fetched once. Downloads run
    a few at a time. Returns how many of the ads ended up with a thumbnail on disk.
    """
    logos = {ad["page_id"]: ad.get("logo_url") for ad in ads if ad.get("page_id")}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        logo_paths = dict(zip(logos, pool.map(
            lambda item: store.save(item[1], f"page_{item[0]}_logo"), logos.items())))
        thumbnails = list(pool.map(
            lambda ad: store.save(ad.get("image_url"), f"ad_{ad['library_id']}_thumb"), ads))
    for ad, thumbnail in zip(ads, thumbnails):
        ad["thumbnail_path"], ad["logo_path"] = thumbnail, logo_paths.get(ad.get("page_id"))
    return sum(bool(path) for path in thumbnails)
