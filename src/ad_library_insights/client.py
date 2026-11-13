"""Fetch Ad Library pages reliably: cache first, throttle, then retry with backoff.

An empty render is ambiguous. If the page itself says the search matched nothing,
that is a real answer ("no_results"). If it shows no cards and no such statement,
the app did not hydrate or the session was turned away ("blocked"), and the fetch
is retried after a growing pause with a longer hydration wait.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urlencode, urlparse

from . import browser, parser
from .storage import DiskCache, Throttle

LIBRARY_URL = "https://www.facebook.com/ads/library/"
ACTIVE_STATUSES = ("active", "inactive", "all")
MEDIA_TYPES = ("all", "image", "meme", "video", "none")


def normalise_country(country: str) -> str:
    code = (country or "").strip().upper()
    if code != "ALL" and not (len(code) == 2 and code.isalpha()):
        raise ValueError("country must be a two-letter ISO code (for example US, IT, DE) or ALL")
    return code


def build_search_url(query: str, country: str, active_status: str = "active",
                     media_type: str = "all") -> str:
    """Public Ad Library keyword-search URL for any query and country."""
    if not (query or "").strip():
        raise ValueError("query must not be empty")
    if active_status not in ACTIVE_STATUSES:
        raise ValueError(f"active_status must be one of {ACTIVE_STATUSES}")
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"media_type must be one of {MEDIA_TYPES}")
    return LIBRARY_URL + "?" + urlencode({
        "active_status": active_status,
        "ad_type": "all",
        "country": normalise_country(country),
        "media_type": media_type,
        "q": query.strip(),
        "search_type": "keyword_unordered",
    })


def is_library_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https"
            and parsed.netloc.lower() in ("www.facebook.com", "facebook.com")
            and parsed.path.startswith("/ads/library"))


@dataclass
class FetchResult:
    url: str
    outcome: str                      # "ok" | "no_results" | "blocked"
    ads: list[dict] = field(default_factory=list)
    results_label: str | None = None
    status_code: int | None = None
    attempts: int = 0
    from_cache: bool = False
    fetched_at: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


class AdLibraryClient:
    """Cache, throttle and retry around a page renderer.

    The renderer, sleeper and jitter source are injectable so the whole policy can
    be exercised offline.
    """

    def __init__(self, cache: DiskCache | None = None, throttle: Throttle | None = None,
                 renderer: Callable[..., Awaitable[browser.PageSnapshot]] = browser.render,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 jitter: Callable[[], float] = random.random,
                 clock: Callable[[], float] = time.time,
                 max_retries: int = 2, backoff_base: float = 20.0, backoff_factor: float = 3.0):
        self.cache = cache
        self.throttle = throttle
        self._renderer = renderer
        self._sleep = sleep
        self._jitter = jitter
        self._clock = clock
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor

    def backoff_delay(self, retry_number: int) -> float:
        """Pause before retry 1, 2, ...: exponential with up to +25% jitter."""
        base = self.backoff_base * self.backoff_factor ** (retry_number - 1)
        return base * (1 + 0.25 * self._jitter())

    async def fetch(self, url: str, wait_seconds: float = 8, scroll_rounds: int = 6,
                    use_cache: bool = True) -> FetchResult:
        if not is_library_url(url):
            raise ValueError("url must be an https://www.facebook.com/ads/library/... link")

        cache_key = f"{url}#scroll={int(scroll_rounds)}"
        if use_cache and self.cache:
            hit = self.cache.get(cache_key)
            if hit:
                return FetchResult(**{**hit, "from_cache": True})

        result = FetchResult(url=url, outcome="blocked")
        for attempt in range(1, self.max_retries + 2):
            if attempt > 1:
                await self._sleep(self.backoff_delay(attempt - 1))
            if self.throttle:
                pause = self.throttle.delay_needed()
                if pause > 0:
                    await self._sleep(pause)
                self.throttle.record()

            result.attempts = attempt
            try:
                # each retry gives the app longer to hydrate
                page = await self._renderer(url, wait_seconds=wait_seconds + 4 * (attempt - 1),
                                            scroll_rounds=scroll_rounds)
            except Exception as exc:  # timeouts, navigation errors, browser crashes
                result.error = f"{type(exc).__name__}: {exc}"
                continue

            result.error = None
            result.status_code = page.status_code
            result.results_label = parser.results_label(page.page_text)
            result.fetched_at = self._clock()
            result.ads = parser.parse_cards(page.cards)
            if result.ads:
                result.outcome = "ok"
                if self.cache:  # empty or blocked pages are never cached
                    self.cache.put(cache_key, asdict(result))
                return result
            if parser.says_no_results(page.page_text):
                result.outcome = "no_results"
                return result
        return result


def default_client() -> AdLibraryClient:
    """Client with the on-disk cache and throttle in the default home directory."""
    return AdLibraryClient(cache=DiskCache(), throttle=Throttle())
