"""Local state shared across runs: a TTL disk cache and a request throttle.

Both live in one directory (``AD_LIBRARY_INSIGHTS_HOME`` or ``~/.ad_library_insights``)
so that a restarted MCP server still remembers what it fetched and how recently.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable


def home_dir() -> Path:
    return Path(os.environ.get("AD_LIBRARY_INSIGHTS_HOME") or Path.home() / ".ad_library_insights")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class DiskCache:
    """One JSON file per key; entries older than ``ttl_seconds`` are ignored."""

    def __init__(self, directory: Path | None = None, ttl_seconds: float = 6 * 3600,
                 clock: Callable[[], float] = time.time):
        self.directory = Path(directory) if directory else home_dir() / "cache"
        self.ttl_seconds = ttl_seconds
        self._clock = clock

    def _path(self, key: str) -> Path:
        return self.directory / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")

    def get(self, key: str) -> dict | None:
        entry = _read_json(self._path(key))
        if not entry or self._clock() - entry.get("stored_at", 0) > self.ttl_seconds:
            return None
        return entry["payload"]

    def put(self, key: str, payload: dict) -> None:
        _write_json(self._path(key), {"stored_at": self._clock(), "key": key, "payload": payload})

    def clear(self) -> int:
        files = list(self.directory.glob("*.json")) if self.directory.exists() else []
        for file in files:
            file.unlink(missing_ok=True)
        return len(files)


class Throttle:
    """Spaces out page renders: a minimum gap plus a rolling hourly budget."""

    def __init__(self, state_file: Path | None = None, min_interval: float = 20.0,
                 max_per_hour: int = 30, clock: Callable[[], float] = time.time):
        self.state_file = Path(state_file) if state_file else home_dir() / "throttle.json"
        self.min_interval = min_interval
        self.max_per_hour = max_per_hour
        self._clock = clock

    def _recent(self) -> list[float]:
        stamps = _read_json(self.state_file) or []
        cutoff = self._clock() - 3600
        return sorted(s for s in stamps if isinstance(s, (int, float)) and s > cutoff)

    def delay_needed(self, min_interval: float | None = None) -> float:
        """Seconds to wait before the next render is allowed.

        ``min_interval`` overrides the usual gap for page loads that belong to the
        same piece of work (a name lookup, then the list, then the detail views).
        """
        recent, now = self._recent(), self._clock()
        if not recent:
            return 0.0
        gap = self.min_interval if min_interval is None else min_interval
        wait = recent[-1] + gap - now
        if len(recent) >= self.max_per_hour:
            wait = max(wait, recent[-self.max_per_hour] + 3600 - now)
        return max(0.0, wait)

    def record(self) -> None:
        """Note that a render is starting now."""
        _write_json(self.state_file, self._recent() + [self._clock()])
