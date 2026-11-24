"""Drive the public Ad Library in headless Chromium.

Three jobs live here, all of them things a visitor does by hand:

* ``render``         open a results page, scroll it, and keep what it shows;
* ``suggest_pages``  type a name in the search box and keep the advertiser suggestions;
* ``DetailSession``  open "See ad details" on chosen ads and keep what the page receives.

The page is a client-rendered app with obfuscated class names. Wherever possible the
data is taken from the JSON the page itself loads (see ``records``); the visible cards
are snapshotted too, as a fallback. Cards are located by content instead of selectors:
every card contains exactly one "Library ID: <digits>" label, and for each label we
climb the DOM until the parent would hold a second one.

The interface locale is pinned to en-US so labels and dates have one known format
regardless of the machine or of the country being researched.
"""
from __future__ import annotations

import base64
import json
import math
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from . import records

LIBRARY_URL = "https://www.facebook.com/ads/library/"

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
_HAS_CARDS_JS = "() => document.body && document.body.innerText.includes('Library ID:')"
_EMBEDDED_JS = """() => [...document.querySelectorAll('script[type="application/json"]')]
    .map((s) => s.textContent).filter((t) => t.includes('search_results_connection'))"""

_EMBEDDED_DETAILS_JS = """() => [...document.querySelectorAll('script[type="application/json"]')]
    .map((s) => s.textContent).filter((t) => t.includes('"ad_details"'))"""

# Tag the "See ad details" (or "See summary details") button of the card with this id.
_MARK_JS = r"""
(id) => {
  document.querySelectorAll('[data-detail-target]').forEach((e) => e.removeAttribute('data-detail-target'));
  const wanted = new RegExp('Library ID:\\s*' + id + '\\b');
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (!wanted.test(node.textContent)) continue;
    let el = node.parentElement;
    for (let depth = 0; depth < 14 && el; depth++, el = el.parentElement) {
      const button = [...el.querySelectorAll('[role=button]')]
        .find((b) => /^See (ad|summary) details$/.test(b.innerText.trim()));
      if (button) {
        button.setAttribute('data-detail-target', '1');
        return /summary/.test(button.innerText) ? 'summary' : 'ad';
      }
    }
  }
  return null;
}
"""

_VIDEO_PAGE = ('<html><body style="margin:0;background:#000"><video id="v" muted playsinline '
               'preload="auto" style="display:block;max-width:480px;max-height:640px"></video></body></html>')
_LOAD_VIDEO_JS = """async (src) => {
  const v = document.getElementById('v');
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('video load timeout')), 20000);
    v.addEventListener('loadeddata', () => { clearTimeout(timer); resolve(); }, { once: true });
    v.addEventListener('error', () => { clearTimeout(timer); reject(new Error('video did not load')); }, { once: true });
    v.src = src;
  });
  return { duration: v.duration, width: v.videoWidth, height: v.videoHeight };
}"""
_SEEK_JS = """async (t) => {
  const v = document.getElementById('v');
  if (Math.abs(v.currentTime - t) < 0.01) return;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('seek timeout')), 10000);
    v.addEventListener('seeked', () => { clearTimeout(timer); resolve(); }, { once: true });
    v.currentTime = t;
  });
}"""

_CONTACT_SHEET_HTML = (
    '<html><body style="margin:0;background:#0f172a">'
    '<canvas id="sheet" style="display:block"></canvas></body></html>'
)
_DRAW_SHEET_JS = """async ({tiles, cols}) => {
  const canvas = document.getElementById('sheet');
  const ctx = canvas.getContext('2d');
  if (!tiles || !tiles.length) return {width: 0, height: 0};
  const imgs = await Promise.all(tiles.map((t) => new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({img, label: t.label || ''});
    img.onerror = () => reject(new Error('tile image failed to load'));
    img.src = t.src;
  })));
  const first = imgs[0].img;
  const nw = first.naturalWidth || 360;
  const nh = first.naturalHeight || 640;
  const tileW = 360;
  const tileH = Math.max(90, Math.min(720, Math.round(tileW * nh / nw)));
  const gutter = 8;
  const pad = 8;
  const nCols = Math.max(1, Math.min(cols || 2, imgs.length));
  const nRows = Math.ceil(imgs.length / nCols);
  const totalW = pad * 2 + nCols * tileW + (nCols - 1) * gutter;
  const totalH = pad * 2 + nRows * tileH + (nRows - 1) * gutter;
  canvas.width = totalW;
  canvas.height = totalH;
  canvas.style.width = totalW + 'px';
  canvas.style.height = totalH + 'px';
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, totalW, totalH);
  ctx.font = 'bold 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  ctx.textBaseline = 'middle';
  for (let i = 0; i < imgs.length; i++) {
    const r = Math.floor(i / nCols);
    const c = i % nCols;
    const x = pad + c * (tileW + gutter);
    const y = pad + r * (tileH + gutter);
    ctx.drawImage(imgs[i].img, x, y, tileW, tileH);
    const label = imgs[i].label;
    if (label) {
      const tw = Math.ceil(ctx.measureText(label).width);
      const bw = tw + 14;
      const bh = 24;
      const bx = x + 8;
      const by = y + 8;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.86)';
      ctx.fillRect(bx, by, bw, bh);
      ctx.strokeStyle = 'rgba(248, 250, 252, 0.35)';
      ctx.lineWidth = 1;
      ctx.strokeRect(bx + 0.5, by + 0.5, bw - 1, bh - 1);
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(label, bx + 7, by + bh / 2);
    }
  }
  return {width: totalW, height: totalH};
}"""
_ANY_JSON_SCRIPTS_JS = """() => [...document.querySelectorAll('script[type="application/json"]')]
    .map((s) => s.textContent).filter(Boolean)"""
_DOM_VIDEO_SRC_JS = """() => {
  const v = document.querySelector('video');
  return v ? (v.currentSrc || v.src || null) : null;
}"""


class DetailError(RuntimeError):
    """An ad's detail view could not be read."""


@dataclass
class PageSnapshot:
    """What one render of an Ad Library URL produced."""

    url: str
    status_code: int | None
    page_text: str
    cards: list[dict] = field(default_factory=list)
    scrolls: int = 0
    edges: list[dict] = field(default_factory=list)   # structured results, in page order
    total_count: int | None = None                    # the library's own count for the search


def _request_field(request, name: str) -> str:
    try:
        return parse_qs(request.post_data or "").get(name, [""])[0]
    except Exception:  # binary or missing body
        return ""


def _is_query(response, friendly_name: str) -> bool:
    return "graphql" in response.url and _request_field(response.request, "fb_api_req_friendly_name") == friendly_name


@asynccontextmanager
async def _chromium(width: int = 1400, height: int = 1600):
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield await browser.new_context(locale="en-US", viewport={"width": width, "height": height})
        finally:
            await browser.close()


async def render(url: str, wait_seconds: float = 8, scroll_rounds: int = 6,
                 timeout_ms: int = 90_000) -> PageSnapshot:
    """Open ``url``, wait for cards, scroll for more, and return everything collected.

    ``wait_seconds`` is the longest we wait for the first card to appear.
    ``scroll_rounds`` is the maximum number of scroll-to-bottom steps; scrolling stops
    early once two consecutive steps add no new cards.
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    async with _chromium() as context:
        page = await context.new_page()
        later_batches: list[str] = []

        async def keep_batches(response):
            if _is_query(response, "AdLibrarySearchPaginationQuery"):
                try:
                    later_batches.append(await response.text())
                except Exception:  # the page moved on before the body was read
                    pass

        page.on("response", keep_batches)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_function(_HAS_CARDS_JS, timeout=max(1, wait_seconds) * 1000)
        except PlaywrightTimeout:
            pass  # no cards: the caller decides whether that means empty or blocked
        await page.wait_for_timeout(1500)

        edges, total = [], None
        for text in await page.evaluate(_EMBEDDED_JS):
            connection = records.connection_from_text(text)
            if connection:
                edges.extend(connection.get("edges") or [])
                total = connection.get("count", total)

        scrolls, stale, seen = 0, 0, await page.evaluate(_COUNT_JS)
        while seen and scrolls < max(0, int(scroll_rounds)) and stale < 2:
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
            scrolls += 1
            now = await page.evaluate(_COUNT_JS)
            stale = stale + 1 if now <= seen else 0
            seen = max(seen, now)

        data = await page.evaluate(_SNAPSHOT_JS)
        for text in later_batches:
            connection = records.connection_from_text(text)
            if connection:
                edges.extend(connection.get("edges") or [])
        return PageSnapshot(
            url=url,
            status_code=response.status if response else None,
            page_text=data["pageText"],
            cards=data["cards"],
            scrolls=scrolls,
            edges=edges,
            total_count=total,
        )


async def suggest_pages(name: str, country: str, timeout_ms: int = 90_000) -> dict | None:
    """Type ``name`` in the library's search box and return the suggestions it loads.

    The return value is the raw response; ``records.pages_from_typeahead`` reads it.
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    def is_answer(response) -> bool:
        if not _is_query(response, "useAdLibraryTypeaheadSuggestionDataSourceQuery"):
            return False
        try:
            return json.loads(_request_field(response.request, "variables")).get("queryString") == name
        except ValueError:
            return False

    # the search box only exists on a results page, so start from a search for the name
    url = LIBRARY_URL + "?" + urlencode({
        "active_status": "active", "ad_type": "all", "country": country, "media_type": "all",
        "q": name, "search_type": "keyword_unordered"})
    async with _chromium() as context:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        box = page.get_by_placeholder(re.compile("keyword or advertiser", re.I)).first
        try:
            await box.wait_for(timeout=20_000)
            async with page.expect_response(is_answer, timeout=20_000) as answer:
                await box.click()
                await box.fill("")
                await box.type(name, delay=60)
            return records.load_payload(await (await answer.value).text())
        except PlaywrightTimeout:
            return None


class DetailSession:
    """One browser page kept open to read the detail view of several ads.

    Opening a detail view makes the page request the ad's transparency data: audience,
    reach by country, the advertiser's page. ``open`` returns that response as received.
    Ads are looked up on the results page at ``url``, scrolling as far as needed; an ad
    that is not listed there is opened through its own address instead.
    """

    def __init__(self, url: str, wait_seconds: float = 12, scroll_rounds: int = 40,
                 open_timeout: float = 15.0, timeout_ms: int = 90_000):
        self.url = url
        self.wait_seconds = wait_seconds
        self.scroll_rounds = scroll_rounds
        self.open_timeout = open_timeout
        self.timeout_ms = timeout_ms
        self._stack = None
        self._context = None
        self._page = None
        self._side = None        # a second tab for single-ad addresses and video frames
        self._scrolls = 0
        self._exhausted = False

    async def __aenter__(self) -> "DetailSession":
        self._stack = _chromium()
        self._context = await self._stack.__aenter__()
        try:
            self._page = await self._context.new_page()
            await self._load(self._page, self.url)
        except BaseException:
            await self._stack.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.__aexit__(*exc)

    async def _load(self, page, url: str) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        try:
            await page.wait_for_function(_HAS_CARDS_JS, timeout=self.wait_seconds * 1000)
        except PlaywrightTimeout as exc:
            raise DetailError("the page served no ad cards") from exc

    async def _side_page(self):
        if self._side is None:
            self._side = await self._context.new_page()
        return self._side

    async def _find(self, library_id: str) -> str | None:
        """Mark the card's button, scrolling the list while it keeps growing."""
        page = self._page
        kind = await page.evaluate(_MARK_JS, library_id)
        stale, seen = 0, await page.evaluate(_COUNT_JS)
        while kind is None and not self._exhausted:
            if self._scrolls >= self.scroll_rounds or stale >= 2:
                self._exhausted = True
                break
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
            self._scrolls += 1
            now = await page.evaluate(_COUNT_JS)
            stale = stale + 1 if now <= seen else 0
            seen = max(seen, now)
            kind = await page.evaluate(_MARK_JS, library_id)
        return kind

    async def _close_dialogs(self, page) -> None:
        """Close every open detail or group view; a view left open hides the list."""
        from playwright.async_api import Error as PlaywrightError

        dialogs = page.get_by_role("dialog")
        for _ in range(6):
            if not await dialogs.count():
                return
            close = dialogs.last.get_by_role("button", name="Close").first
            try:   # the group view ignores Escape, so use its own button when there is one
                if await close.count():
                    await close.click(timeout=3000)
                else:
                    await page.keyboard.press("Escape")
            except PlaywrightError:
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        if await dialogs.count():
            raise DetailError("a detail view would not close")

    async def _click_through(self, page, kind: str) -> dict:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        budget = self.open_timeout * 1000
        try:
            async with page.expect_response(
                    lambda r: _is_query(r, "AdLibraryV3AdDetailsQuery"), timeout=budget) as answer:
                await page.locator("[data-detail-target]").first.click(timeout=budget)
                if kind == "summary":  # a group of ads: step into its first member
                    inner = page.get_by_role("dialog").last.get_by_role("button", name="See ad details")
                    await inner.first.click(timeout=budget)
            payload = records.load_payload(await (await answer.value).text())
        except PlaywrightTimeout as exc:
            raise DetailError("the detail view did not answer in time") from exc
        finally:
            await self._close_dialogs(page)
        if not isinstance(records.find_key(payload, "ad_details"), dict):
            raise DetailError("the detail view answered without ad details")
        return payload

    async def open(self, library_id: str) -> dict:
        """The detail response for one ad."""
        library_id = str(library_id)
        await self._close_dialogs(self._page)
        kind = await self._find(library_id)
        if kind:
            return await self._click_through(self._page, kind)
        # An ad's own address opens its detail view straight away, with the data
        # already inside the page instead of in a later response.
        side = await self._side_page()
        await self._load(side, records.AD_URL.format(library_id))
        for text in await side.evaluate(_EMBEDDED_DETAILS_JS):
            details = records.find_key(records.load_payload(text), "ad_details")
            if isinstance(details, dict):
                return {"data": {"ad_library_main": {"ad_details": details}}}
        await self._close_dialogs(side)
        kind = await side.evaluate(_MARK_JS, library_id)
        if not kind:
            raise DetailError("the ad is no longer listed")
        return await self._click_through(side, kind)

    async def frames(self, video_url: str, stem: Path, fractions=(0.02, 0.5, 0.97)) -> list[str]:
        """Save still frames of a video (start, middle, end) as ``<stem>_1.jpg`` and so on.

        The video is loaded on its own in a blank tab, so the frames carry no player
        controls or overlays.
        """
        from playwright.async_api import Error as PlaywrightError

        side = await self._side_page()
        saved = []
        try:
            await side.set_content(_VIDEO_PAGE)
            meta = await side.evaluate(_LOAD_VIDEO_JS, video_url)
            duration = float(meta.get("duration") or 0)
            if not math.isfinite(duration) or duration <= 0:      # 0, NaN or inf: nothing to seek
                return saved
            meta_path = Path(f"{stem}_meta.json")
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            raw_w, raw_h = meta.get("width") or 0, meta.get("height") or 0
            meta_path.write_text(
                json.dumps({
                    "duration": round(duration, 2),
                    "width": int(raw_w) if raw_w > 0 else None,
                    "height": int(raw_h) if raw_h > 0 else None,
                }),
                encoding="utf-8",
            )
            video = side.locator("#v")
            for index, fraction in enumerate(fractions, start=1):
                await side.evaluate(_SEEK_JS, duration * fraction)
                await side.wait_for_timeout(200)
                path = Path(f"{stem}_{index}.jpg")
                path.parent.mkdir(parents=True, exist_ok=True)
                await video.screenshot(path=str(path), type="jpeg", quality=72)
                saved.append(str(path))
        except PlaywrightError:
            pass  # a video that will not play gives fewer frames, never a failed ad
        return saved


def _sheet_ts(seconds: float) -> str:
    tenths = round(max(0.0, float(seconds)) * 10)
    mins, rem = divmod(tenths, 600)
    return f"{mins:02d}:{rem / 10.0:04.1f}"


async def compose_contact_sheet(page, tiles: list[dict], output_path: Path, cols: int = 2) -> str | None:
    """Render local JPEG frames onto a same-origin canvas grid with timestamp labels."""
    if not tiles:
        return None
    encoded = []
    for tile in tiles:
        raw = Path(tile["path"]).read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        encoded.append({"src": f"data:image/jpeg;base64,{b64}", "label": tile.get("label", "")})
    await page.set_content(_CONTACT_SHEET_HTML)
    await page.evaluate(_DRAW_SHEET_JS, {"tiles": encoded, "cols": max(1, int(cols))})
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await page.locator("#sheet").screenshot(path=str(output_path), type="jpeg", quality=82)
    return str(output_path)


async def fetch_ad_video(ad_id: str, timeout_ms: int = 60_000) -> dict:
    """Open one ad's public Library URL to read a fresh video address and copy."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    ad_id = str(ad_id)
    url = records.AD_URL.format(ad_id)
    chosen: dict | None = None
    dom_video: str | None = None
    async with _chromium() as context:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_function(
                "() => document.body && (document.body.innerText.includes('Library ID:') || !!document.querySelector('video'))",
                timeout=8_000,
            )
        except PlaywrightTimeout:
            pass
        await page.wait_for_timeout(1200)

        for text in await page.evaluate(_EMBEDDED_JS):
            connection = records.connection_from_text(text)
            if not connection:
                continue
            ads = records.ads_from_edges(connection.get("edges") or [])
            match = next(
                (ad for ad in ads if ad.get("library_id") == ad_id or ad_id in (ad.get("collation_ids") or [])),
                ads[0] if ads else None,
            )
            if match:
                chosen = match
                break

        if chosen is None or not chosen.get("video_url"):
            for text in await page.evaluate(_ANY_JSON_SCRIPTS_JS):
                if ad_id not in text and '"snapshot"' not in text:
                    continue
                payload = records.load_payload(text)
                if not payload:
                    continue
                snap = records.find_key(payload, "snapshot")
                if isinstance(snap, dict):
                    candidate = records.ad_from_record({"ad_archive_id": ad_id, "snapshot": snap})
                    if candidate:
                        if chosen is None:
                            chosen = candidate
                        elif candidate.get("video_url") and not chosen.get("video_url"):
                            chosen["video_url"] = candidate["video_url"]
                if chosen and not chosen.get("video_url"):
                    fallback_url = records.find_key(payload, "video_hd_url") or records.find_key(payload, "video_sd_url")
                    if isinstance(fallback_url, str) and fallback_url.startswith("https://"):
                        chosen["video_url"] = fallback_url
                if chosen and chosen.get("video_url"):
                    break

        dom_video = await page.evaluate(_DOM_VIDEO_SRC_JS)

    video_url = (chosen or {}).get("video_url") or (dom_video if isinstance(dom_video, str) and dom_video.startswith("https://") else None)
    media_type = (chosen or {}).get("media_type") or ("video" if video_url else None)
    return {
        "found": bool(chosen or video_url),
        "ad_id": ad_id,
        "media_type": media_type,
        "video_url": video_url,
        "body": (chosen or {}).get("body") or "",
        "headline": (chosen or {}).get("headline"),
        "cta": (chosen or {}).get("cta"),
        "advertiser": (chosen or {}).get("advertiser"),
        "started": (chosen or {}).get("started"),
    }


async def capture_video_frames(video_url: str, frames_dir: Path, timestamps_fn, sheets_dir: Path) -> dict:
    """Seek a Meta video URL in Chromium, screenshot frames without CORS taint, and compose contact sheets."""
    from playwright.async_api import Error as PlaywrightError

    frames_dir = Path(frames_dir)
    sheets_dir = Path(sheets_dir)
    async with _chromium() as context:
        page = await context.new_page()
        try:
            await page.set_content(_VIDEO_PAGE)
            meta = await page.evaluate(_LOAD_VIDEO_JS, video_url)
            duration = float(meta.get("duration") or 0)
            if not math.isfinite(duration) or duration <= 0:
                raise RuntimeError("video duration is invalid")
            raw_w, raw_h = meta.get("width") or 0, meta.get("height") or 0
            clean_w = int(raw_w) if raw_w > 0 else None
            clean_h = int(raw_h) if raw_h > 0 else None
            hook_times, body_times = timestamps_fn(duration)

            frames_dir.mkdir(parents=True, exist_ok=True)
            for stale in frames_dir.glob("*.jpg"):
                stale.unlink(missing_ok=True)

            video = page.locator("#v")
            captured: list[dict] = []
            plan = [("hook", float(t)) for t in hook_times] + [("body", float(t)) for t in body_times]
            for idx, (zone, ts) in enumerate(plan, start=1):
                await page.evaluate(_SEEK_JS, ts)
                await page.wait_for_timeout(180)
                frame_path = frames_dir / f"{idx:02d}_{ts:04.1f}s.jpg"
                await video.screenshot(path=str(frame_path), type="jpeg", quality=78)
                label = f"#{idx} · {_sheet_ts(ts)}"
                captured.append({"index": idx, "timestamp": round(ts, 2), "label": label,
                                 "zone": zone, "path": str(frame_path)})

            sheets: list[dict] = []
            hook_tiles = [f for f in captured if f["zone"] == "hook"]
            if hook_tiles:
                hook_sheet = await compose_contact_sheet(page, hook_tiles, sheets_dir / "hook_sheet.jpg", cols=2)
                if hook_sheet:
                    sheets.append({"zone": "hook", "path": hook_sheet, "frames": len(hook_tiles)})
            body_tiles = [f for f in captured if f["zone"] == "body"]
            if body_tiles:
                body_sheet = await compose_contact_sheet(page, body_tiles, sheets_dir / "body_sheet.jpg", cols=3)
                if body_sheet:
                    sheets.append({"zone": "body", "path": body_sheet, "frames": len(body_tiles)})
        except PlaywrightError as exc:
            raise RuntimeError(f"video frame capture failed: {exc}") from exc

    return {
        "ok": True,
        "duration": round(duration, 2),
        "width": clean_w,
        "height": clean_h,
        "frames": captured,
        "contact_sheets": sheets,
    }
