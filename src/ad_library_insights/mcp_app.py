"""MCP App UI resource builder and media staging helpers (SEP-1865)."""
from __future__ import annotations

import base64
import json
import re
import shutil
from pathlib import Path

APP_URI = "ui://ad-library-insights/studio.html"
INLINE_META = {"ui": {"resourceUri": APP_URI, "visibility": ["model", "app"]}}
PANE_META = {
    "ui": {"resourceUri": APP_URI, "visibility": ["model", "app"]},
    "com.google.antigravity/ui": {
        "entrypoints": [
            {"type": "aux_pane", "title": "Ad Library Studio"},
            {"type": "global", "title": "Ad Library Studio"},
        ]
    },
}
APP_ONLY_META = {"ui": {"visibility": ["app"]}}
MODEL_AND_APP_META = {"ui": {"visibility": ["model", "app"]}}

STATIC_DIR = Path(__file__).parent / "web" / "static"
MAX_MEDIA_BYTES = 1_500_000
_SAFE_NAME = re.compile(r"^[\w.-]+$")
_SCRIPT_CLOSE = re.compile(r"</(script)", re.IGNORECASE)
_STYLE_CLOSE = re.compile(r"</(style)", re.IGNORECASE)
_CSS_COMMENTS = re.compile(r"/\*.*?\*/", re.S)


def _compact_css(raw: str) -> str:
    stripped = _CSS_COMMENTS.sub("", raw)
    return "\n".join(line.strip() for line in stripped.splitlines() if line.strip())


def build_studio_html(static_dir: Path | None = None) -> str:
    """Assemble the self-contained MCP App HTML document from web static assets."""
    root = Path(static_dir) if static_dir else STATIC_DIR
    css = _STYLE_CLOSE.sub(r"<\\/\1", _compact_css((root / "app.css").read_text(encoding="utf-8")))
    strings_raw = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    strings_json = json.dumps(strings_raw, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    sdk_js = _SCRIPT_CLOSE.sub(r"<\\/\1", (root / "mcp_ext_apps.min.js").read_text(encoding="utf-8"))
    app_js = _SCRIPT_CLOSE.sub(r"<\\/\1", (root / "app.js").read_text(encoding="utf-8"))

    return (
        '<!doctype html>\n'
        '<html lang="it" data-theme="light">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Ad Library Insights — Studio</title>\n'
        f'<style>{css}</style>\n'
        '</head>\n'
        '<body class="mcp-host">\n'
        '<header class="topbar">\n'
        '  <div class="topbar-in">\n'
        '    <span class="brand"><span class="brand-mark" aria-hidden="true">'
        '<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="2">'
        '<path d="M3 14V9.5M7 14V5.5M11 14V8M15 14V3.5" stroke-linecap="round"/></svg>'
        '</span><span class="brand-text">Ad Library Studio <em class="brand-by">by Klaus</em></span></span>\n'
        '    <nav class="modes" id="modes" aria-label="Mode"></nav>\n'
        '    <button class="btn quiet small top-tut" id="tut-btn" data-action="tutorial"></button>\n'
        '    <div class="switch" id="lang" role="group"></div>\n'
        '    <div class="switch" id="theme" role="group"></div>\n'
        '  </div>\n'
        '</header>\n'
        '<section class="search" id="search"></section>\n'
        '<main class="page" id="results"></main>\n'
        '<div id="overlay"></div>\n'
        f'<script>window.__MCP_APP_MODE__=true;window.__STRINGS__={strings_json};</script>\n'
        f'<script>{sdk_js}</script>\n'
        f'<script>{app_js}</script>\n'
        '</body>\n'
        '</html>'
    )


def media_data_uri(media_dir: Path, filename: str) -> str | None:
    """Safely read an image inside ``media_dir`` and return a base64 ``data:`` URI."""
    name = str(filename or "").strip()
    if not name or "/" in name or "\\" in name or not _SAFE_NAME.match(name):
        return None
    base = Path(media_dir).resolve()
    target = (base / name).resolve()
    if target.parent != base or not target.is_file():
        return None
    try:
        raw = target.read_bytes()
    except OSError:
        return None
    if not raw or len(raw) > MAX_MEDIA_BYTES:
        return None
    ext = target.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def stage_video_sheets(res: dict, ad_id: str, media_dir: Path) -> dict:
    """Copy hook/body contact sheets into ``media_dir`` and return a path-free summary."""
    if not res.get("ok"):
        return {
            "ok": False,
            "ad_id": ad_id,
            "outcome": res.get("outcome") or "unavailable",
            "note": res.get("note") or "Video unavailable.",
        }

    base = Path(media_dir)
    base.mkdir(parents=True, exist_ok=True)
    staged: dict[str, str | None] = {"hook": None, "body": None}
    for sheet in res.get("contact_sheets") or []:
        kind = sheet.get("kind")
        src = Path(sheet.get("path") or "")
        if kind in staged and src.is_file():
            dst_name = f"vid_{ad_id}_{kind}.jpg"
            dst = base / dst_name
            if src.resolve() != dst.resolve():
                shutil.copyfile(src, dst)
            staged[kind] = dst_name

    return {
        "ok": True,
        "ad_id": res.get("ad_id") or ad_id,
        "duration": res.get("duration"),
        "width": res.get("width"),
        "height": res.get("height"),
        "aspect_ratio": res.get("aspect_ratio"),
        "hook_sheet_name": staged["hook"],
        "body_sheet_name": staged["body"],
        "from_cache": bool(res.get("from_cache")),
    }


def _media_ref(path: str | None, url_prefix: str) -> str | None:
    if not path:
        return None
    name = Path(path).name
    return f"{url_prefix}{name}" if url_prefix else name


def compact_result(result: dict, params: dict | None = None, url_prefix: str = "") -> dict:
    """Path-free studio representation of a research result for MCP App or web UI."""
    shown = {k: v for k, v in result.items() if k not in ("ads", "page")}
    shown["ads"] = []
    for ad in result.get("ads", []):
        row = {
            k: v
            for k, v in ad.items()
            if k not in ("image_url", "logo_url", "video_url", "thumbnail_path", "logo_path")
        }
        row["thumbnail"] = _media_ref(ad.get("thumbnail_path"), url_prefix)
        row["logo"] = _media_ref(ad.get("logo_path"), url_prefix)
        row["frames"] = [_media_ref(path, url_prefix) for path in ad.get("frames") or []]
        shown["ads"].append(row)
    if result.get("page"):
        page = {k: v for k, v in result["page"].items() if k not in ("logo_url", "logo_path")}
        page["logo"] = _media_ref(result["page"].get("logo_path"), url_prefix)
        shown["page"] = page
    if params is not None:
        shown["request"] = params
    return shown

