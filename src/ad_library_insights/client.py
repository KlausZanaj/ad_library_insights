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

from . import browser, parser, records
from .details import DetailCollector
from .media import MediaStore
from .storage import DiskCache, Throttle

LIBRARY_URL = "https://www.facebook.com/ads/library/"
ACTIVE_STATUSES = ("active", "inactive", "all")
MEDIA_TYPES = ("all", "image", "meme", "video", "none")
# The list is asked for in the order the rating relies on: most impressions first.
SORT_BY_IMPRESSIONS = {"sort_data[mode]": "total_impressions", "sort_data[direction]": "desc"}


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
        **SORT_BY_IMPRESSIONS,
    })


def build_page_url(page_id: str, country: str, active_status: str = "active",
                   media_type: str = "all") -> str:
    """Ad Library URL listing every ad of one advertiser page in a country."""
    page_id = str(page_id or "").strip()
    if not page_id.isdigit():
        raise ValueError("page_id must be the numeric id of an advertiser page")
    if active_status not in ACTIVE_STATUSES:
        raise ValueError(f"active_status must be one of {ACTIVE_STATUSES}")
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"media_type must be one of {MEDIA_TYPES}")
    return LIBRARY_URL + "?" + urlencode({
        "active_status": active_status,
        "ad_type": "all",
        "country": normalise_country(country),
        "media_type": media_type,
        "search_type": "page",
        "view_all_page_id": page_id,
        **SORT_BY_IMPRESSIONS,
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
    total_count: int | None = None    # the count the library itself gives for the search
    source: str = "cards"             # "structured" (page data) or "cards" (visible text)

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
                 max_retries: int = 2, backoff_base: float = 20.0, backoff_factor: float = 3.0,
                 suggester: Callable[..., Awaitable[dict | None]] = browser.suggest_pages,
                 session_factory: Callable[..., object] = browser.DetailSession,
                 media: MediaStore | None = None, follow_up_gap: float = 5.0):
        self.cache = cache
        self.throttle = throttle
        self.media = media or MediaStore()
        self.follow_up_gap = follow_up_gap
        self._suggester = suggester
        self._session_factory = session_factory
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
            # the data the page loaded first; the visible cards if it is missing
            result.ads = records.ads_from_edges(page.edges)
            result.source = "structured" if result.ads else "cards"
            result.total_count = page.total_count
            if not result.ads:
                result.ads = parser.parse_cards(page.cards)
                for position, ad in enumerate(result.ads, start=1):     # the page order is by impressions
                    ad.setdefault("impression_rank", position)
            if result.ads:
                result.outcome = "ok"
                if self.cache:  # empty or blocked pages are never cached
                    self.cache.put(cache_key, asdict(result))
                return result
            if parser.says_no_results(page.page_text):
                result.outcome = "no_results"
                return result
        return result


    async def _follow_up_slot(self) -> None:
        """Wait for a turn; page loads that continue one job need only a short gap."""
        if self.throttle:
            pause = self.throttle.delay_needed(self.follow_up_gap)
            if pause > 0:
                await self._sleep(pause)
            self.throttle.record()

    async def find_pages(self, name: str, country: str, use_cache: bool = True) -> list[dict]:
        """Advertiser pages the library suggests for ``name``: id, name, followers, category."""
        name = (name or "").strip()
        if not name:
            raise ValueError("name must not be empty")
        country = normalise_country(country)
        cache_key = f"pages:{country}:{name.casefold()}"
        if use_cache and self.cache:
            hit = self.cache.get(cache_key)
            if hit:
                return hit["pages"]
        pages: list[dict] = []
        for attempt in range(1, self.max_retries + 2):
            if attempt > 1:
                await self._sleep(self.backoff_delay(attempt - 1))
            await self._follow_up_slot()
            try:
                payload = await self._suggester(name, country)
            except Exception:  # navigation errors, browser crashes
                continue
            if payload is not None:
                pages = records.pages_from_typeahead(payload)
                break
        if pages and self.cache:
            self.cache.put(cache_key, {"pages": pages})
        return pages

    async def read_details(self, url: str, library_ids: list[str], country: str | None = None,
                           videos: dict[str, str] | None = None, on_progress=None,
                           use_cache: bool = True, scroll_rounds: int = 40) -> dict[str, dict]:
        """Reach and audience of the given ads, read from their detail views.

        ``url`` is the results page the ads are listed on. ``videos`` maps library ids
        to video addresses for which three still frames should be saved. Returns
        ``{library_id: {"ok", "details" | "error", "attempts", "from_cache", "frames"}}``.
        A browser is opened only if something is missing from the cache.
        """
        if not is_library_url(url):
            raise ValueError("url must be an https://www.facebook.com/ads/library/... link")
        ids = [str(i) for i in library_ids]
        videos = {str(k): v for k, v in (videos or {}).items() if v}
        collector = DetailCollector(cache=self.cache, sleep=self._sleep, jitter=self._jitter,
                                    clock=self._clock)
        to_read = [i for i in ids if not (use_cache and collector.cached(i, country) is not None)]
        to_frame = [i for i in videos if not self.media.frames(i)]

        if not to_read and not to_frame:
            results = await collector.collect(None, ids, country, on_progress, use_cache=True)
        else:
            results, error = None, None
            for attempt in range(1, self.max_retries + 2):
                if attempt > 1:
                    await self._sleep(self.backoff_delay(attempt - 1))
                await self._follow_up_slot()
                try:
                    async with self._session_factory(url, scroll_rounds=scroll_rounds) as session:
                        results = await collector.collect(session, ids, country, on_progress, use_cache)
                        for library_id in to_frame:
                            await session.frames(videos[library_id], self.media.frame_stem(library_id))
                    break
                except Exception as exc:  # the results page itself did not load
                    error = f"{type(exc).__name__}: {exc}"
            if results is None:
                results = {i: {"ok": False, "error": error, "attempts": 0, "from_cache": False}
                           for i in ids}
        for library_id, outcome in results.items():
            outcome["frames"] = self.media.frames(library_id) if library_id in videos else []
        return results


def default_client() -> AdLibraryClient:
    """Client with the on-disk cache and throttle in the default home directory."""
    return AdLibraryClient(cache=DiskCache(), throttle=Throttle())
