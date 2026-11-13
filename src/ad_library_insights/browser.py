"""Render an Ad Library page in headless Chromium and snapshot its ad cards.

The page is a client-rendered, infinite-scroll app with obfuscated class names, so
cards are located by content instead of selectors: every card contains exactly one
"Library ID: <digits>" label. For each label we climb the DOM until the parent would
hold a second label; the last element before that is the card.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_SNAPSHOT_JS = r"""
() => {
  const labels = (el) => (el.innerText.match(/Library ID:/g) || []).length;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const cards = new Set();
  let node;
  while ((node = walker.nextNode())) {
    if (!/Library ID:\s*\d+/.test(node.textContent)) continue;
    let el = node.parentElement;
    while (el.parentElement && labels(el.parentElement) <= 1) el = el.parentElement;
    cards.add(el);
  }
  return {
    pageText: document.body.innerText.slice(0, 4000),
    cards: [...cards].map((card) => ({
      text: card.innerText,
      links: [...card.querySelectorAll('a[href]')].map((a) => ({ href: a.href, text: a.innerText })),
      images: [...card.querySelectorAll('img[src]')].map((img) => img.src),
      videos: [...card.querySelectorAll('video')].map((v) => v.poster || v.src || ''),
    })),
  };
}
"""

_COUNT_JS = "() => (document.body.innerText.match(/Library ID:/g) || []).length"


@dataclass
class PageSnapshot:
    """What one render of an Ad Library URL produced."""

    url: str
    status_code: int | None
    page_text: str
    cards: list[dict] = field(default_factory=list)
    scrolls: int = 0


async def render(url: str, wait_seconds: float = 8, scroll_rounds: int = 6,
                 timeout_ms: int = 90_000) -> PageSnapshot:
    """Open ``url``, wait for cards, scroll for more, and return the raw card data.

    ``wait_seconds`` is the longest we wait for the first card to appear.
    ``scroll_rounds`` is the maximum number of scroll-to-bottom steps; scrolling stops
    early once two consecutive steps add no new cards.

    The UI locale is pinned to en-US so labels and dates have one known format
    regardless of the machine or of the country being researched.
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale="en-US", viewport={"width": 1400, "height": 1600})
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_function(
                    "() => document.body && document.body.innerText.includes('Library ID:')",
                    timeout=max(1, wait_seconds) * 1000)
            except PlaywrightTimeout:
                pass  # no cards: the caller decides whether that means empty or blocked
            await page.wait_for_timeout(1500)

            scrolls, stale, seen = 0, 0, await page.evaluate(_COUNT_JS)
            while seen and scrolls < max(0, int(scroll_rounds)) and stale < 2:
                await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)
                scrolls += 1
                now = await page.evaluate(_COUNT_JS)
                stale = stale + 1 if now <= seen else 0
                seen = max(seen, now)

            data = await page.evaluate(_SNAPSHOT_JS)
            return PageSnapshot(
                url=url,
                status_code=response.status if response else None,
                page_text=data["pageText"],
                cards=data["cards"],
                scrolls=scrolls,
            )
        finally:
            await browser.close()
