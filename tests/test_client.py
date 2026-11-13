import asyncio

import pytest

from ad_library_insights import client as client_module
from ad_library_insights.browser import PageSnapshot
from ad_library_insights.client import AdLibraryClient, build_search_url, is_library_url
from ad_library_insights.storage import DiskCache, Throttle

URL = "https://www.facebook.com/ads/library/?country=DE&q=desk"
EMPTY = "Log in"
NO_RESULTS = "0 results\nNo ads match your search"


class Harness:
    """A client wired to a scripted renderer, a fake clock and a recording sleeper."""

    def __init__(self, tmp_path, pages, cards, **options):
        self.now = 1_000_000.0
        self.sleeps: list[float] = []
        self.calls: list[dict] = []
        self._pages = list(pages)
        self._cards = cards
        clock = lambda: self.now
        self.cache = DiskCache(tmp_path / "cache", ttl_seconds=3600, clock=clock)
        self.throttle = Throttle(tmp_path / "throttle.json", min_interval=20, max_per_hour=3, clock=clock)
        self.client = AdLibraryClient(
            cache=self.cache, throttle=self.throttle, renderer=self._render, sleep=self._sleep,
            jitter=lambda: 0.0, clock=clock, **options)

    async def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    async def _render(self, url, wait_seconds, scroll_rounds):
        self.calls.append({"wait_seconds": wait_seconds, "scroll_rounds": scroll_rounds})
        page = self._pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return PageSnapshot(url=url, status_code=403, page_text=page,
                            cards=self._cards if page == "ok" else [])

    def fetch(self, **kwargs):
        return asyncio.run(self.client.fetch(URL, **kwargs))


def test_success_first_time(tmp_path, cards):
    h = Harness(tmp_path, ["ok"], cards)
    result = h.fetch()
    assert result.ok and result.attempts == 1 and not result.from_cache
    assert len(result.ads) == 3
    assert h.sleeps == []


def test_second_call_is_served_from_cache(tmp_path, cards):
    h = Harness(tmp_path, ["ok"], cards)
    h.fetch()
    again = h.fetch()
    assert again.from_cache and again.ok and len(again.ads) == 3
    assert len(h.calls) == 1


def test_cache_expires_and_can_be_bypassed(tmp_path, cards):
    h = Harness(tmp_path, ["ok", "ok", "ok"], cards)
    h.fetch()
    h.now += 30
    assert not h.fetch(use_cache=False).from_cache
    h.now += 3601
    assert not h.fetch().from_cache
    assert len(h.calls) == 3


def test_blocked_page_is_retried_with_backoff_and_longer_wait(tmp_path, cards):
    h = Harness(tmp_path, [EMPTY, EMPTY, "ok"], cards, backoff_base=20, backoff_factor=3)
    result = h.fetch(wait_seconds=8)
    assert result.ok and result.attempts == 3
    assert h.sleeps == [20, 60]
    assert [c["wait_seconds"] for c in h.calls] == [8, 12, 16]


def test_gives_up_as_blocked_and_does_not_cache(tmp_path, cards):
    h = Harness(tmp_path, [EMPTY, EMPTY, EMPTY, "ok"], cards)
    result = h.fetch()
    assert result.outcome == "blocked" and result.attempts == 3 and result.ads == []
    assert h.cache.get(f"{URL}#scroll=6") is None


def test_genuine_no_results_is_not_retried(tmp_path, cards):
    h = Harness(tmp_path, [NO_RESULTS, "ok"], cards)
    result = h.fetch()
    assert result.outcome == "no_results" and result.attempts == 1
    assert h.sleeps == []


def test_renderer_exception_counts_as_failed_attempt(tmp_path, cards):
    h = Harness(tmp_path, [TimeoutError("navigation"), "ok"], cards)
    result = h.fetch()
    assert result.ok and result.attempts == 2 and result.error is None

    h2 = Harness(tmp_path / "b", [TimeoutError("navigation")] * 3, cards)
    failed = h2.fetch()
    assert failed.outcome == "blocked" and "TimeoutError" in failed.error


def test_throttle_spaces_consecutive_renders(tmp_path, cards):
    h = Harness(tmp_path, ["ok", "ok"], cards)
    h.fetch()
    h.now += 5
    h.fetch(use_cache=False)
    assert h.sleeps == [15]


def test_backoff_jitter_adds_at_most_a_quarter():
    client = AdLibraryClient(jitter=lambda: 1.0, backoff_base=20, backoff_factor=3)
    assert client.backoff_delay(1) == 25
    assert client.backoff_delay(2) == 75


def test_rejects_urls_outside_the_ad_library(tmp_path, cards):
    h = Harness(tmp_path, [], cards)
    with pytest.raises(ValueError):
        asyncio.run(h.client.fetch("https://example.com/ads/library/"))
    assert is_library_url(URL)
    assert not is_library_url("http://www.facebook.com/ads/library/")
    assert not is_library_url("https://www.facebook.com/somepage")


def test_build_search_url_takes_any_query_and_country():
    url = build_search_url("caffè in grani", "it", "all", "video")
    assert url.startswith(client_module.LIBRARY_URL + "?")
    assert "country=IT" in url and "q=caff%C3%A8+in+grani" in url
    assert "active_status=all" in url and "media_type=video" in url


@pytest.mark.parametrize("query,country", [("", "US"), ("desk", "USA"), ("desk", ""), ("desk", "1T")])
def test_build_search_url_validates_input(query, country):
    with pytest.raises(ValueError):
        build_search_url(query, country)
