"""On-demand deep video inspection: hook-first contact sheets, metadata and optional local audio.

Browser frame capture runs through Playwright ``video.screenshot()`` and local
``data:image/jpeg;base64,...`` canvas composition so Meta CDN video origins never
trigger cross-origin canvas taint. Audio transcription is strictly optional behind the
``.[video]`` extra (``faster-whisper`` + ``av``) and uses ``local_files_only=True`` inside
MCP calls so a missing model never triggers a client timeout.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import browser
from .storage import home_dir

MAX_VIDEO_BYTES = 50_000_000
DOWNLOAD_TIMEOUT = 30.0
ALLOWED_VIDEO_DOMAINS = ("fbcdn.net", "fbsbx.com")
WHISPER_MODELS = ("tiny", "base", "small", "medium")
DEFAULT_WHISPER_MODEL = "base"
UNTRUSTED_OPEN = "<untrusted_ad_content>"
UNTRUSTED_CLOSE = "</untrusted_ad_content>"

_UNTRUSTED_TAG_RE = re.compile(r"<(/?)\s*untrusted_ad_content\s*>", re.IGNORECASE)
_STANDARD_RATIOS = (
    ("9:16", 9 / 16),
    ("4:5", 4 / 5),
    ("2:3", 2 / 3),
    ("1:1", 1.0),
    ("4:3", 4 / 3),
    ("16:9", 16 / 9),
)


def validate_ad_id(ad_id: str) -> str:
    """Ensure ``ad_id`` is a plain ASCII numeric Ad Library ID (blocks arbitrary URLs or paths)."""
    raw = str(ad_id or "").strip()
    if not raw.isascii() or not raw.isdigit() or not (5 <= len(raw) <= 25):
        raise ValueError("ad_id must be a numeric Ad Library ID (5 to 25 ASCII digits)")
    return raw


def validate_whisper_model(model_size: str) -> str:
    clean = (model_size or "").strip().lower()
    if clean not in WHISPER_MODELS:
        raise ValueError(f"whisper_model must be one of {WHISPER_MODELS}")
    return clean


def is_allowed_video_url(url: str | None) -> bool:
    """Allow only credential-free HTTPS addresses hosted on Meta video CDN domains."""
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return bool(host) and any(host == dom or host.endswith("." + dom) for dom in ALLOWED_VIDEO_DOMAINS)


def format_aspect_ratio(width: int | None, height: int | None) -> str | None:
    """Snap near-standard social video dimensions to common ratios, else reduced ``W:H``."""
    if (
        isinstance(width, bool) or isinstance(height, bool)
        or not isinstance(width, (int, float)) or not isinstance(height, (int, float))
        or not math.isfinite(width) or not math.isfinite(height)
    ):
        return None
    w, h = int(width), int(height)
    if w <= 0 or h <= 0:
        return None
    ratio = w / h
    best_label, best_diff = min(
        ((label, abs(ratio - target) / target) for label, target in _STANDARD_RATIOS),
        key=lambda item: item[1],
    )
    if best_diff <= 0.04:
        return best_label
    divisor = math.gcd(w, h)
    return f"{w // divisor}:{h // divisor}"


def format_timestamp(seconds: float) -> str:
    """Format seconds as ``MM:SS.d`` with carry-safe tenth-second rounding."""
    tenths = round(max(0.0, float(seconds)) * 10)
    mins, rem_tenths = divmod(tenths, 600)
    return f"{mins:02d}:{rem_tenths / 10.0:04.1f}"


def _dedup_points(points: list[float], low: float, high: float, min_gap: float = 0.15) -> list[float]:
    kept: list[float] = []
    for pt in points:
        clamped = round(min(high, max(low, float(pt))), 2)
        if not kept or clamped - kept[-1] >= min_gap:
            kept.append(clamped)
    return kept


def plan_timestamps(duration: float) -> tuple[list[float], list[float]]:
    """Return asymmetric hook-first timestamps ``(hook_times, body_times)`` for ``duration`` seconds."""
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("duration must be a positive finite number")
    d = float(duration)
    if not math.isfinite(d) or d <= 0:
        raise ValueError("duration must be a positive finite number")

    if d <= 4.0:
        if d < 0.6:
            pts = sorted({round(d * frac, 2) for frac in (0.15, 0.5, 0.85) if 0 < d * frac < d})
            return (pts or [round(d * 0.5, 2)], [])
        low = round(min(0.2, d * 0.08), 2)
        high = round(max(low + 0.1, d * 0.92), 2)
        raw = [low + (high - low) * i / 3 for i in range(4)]
        return (_dedup_points(raw, low, min(d - 0.03, high)), [])

    if d <= 10.0:
        hook = _dedup_points([0.3, 1.5, 3.0], 0.05, d - 0.1)
        close_2 = round(min(d - 0.05, d * 0.97), 2)
        span = close_2 - hook[-1]
        count = min(6, max(1, int(span / 0.6)))
        body = [round(hook[-1] + span * k / count, 2) for k in range(1, count + 1)]
        return (hook, body)

    hook = _dedup_points([0.3, 1.5, 3.0, 5.0], 0.05, d - 0.1)

    close_2 = round(min(d - 0.05, d * 0.97), 2)
    close_gap = min(4.0, max(1.5, d * 0.09))
    close_1 = round(max(hook[-1] + 0.4, close_2 - close_gap), 2)
    interior = [hook[-1] + (close_1 - hook[-1]) * k / 5 for k in range(1, 5)]

    body: list[float] = []
    prev = hook[-1]
    upper = d - 0.03
    for pt in interior:
        val = round(pt, 2)
        if prev + 0.15 <= val <= close_1 - 0.15 and val <= upper:
            body.append(val)
            prev = val
    for endpoint in (close_1, close_2):
        val = round(endpoint, 2)
        if prev + 0.15 <= val <= upper:
            body.append(val)
            prev = val
    return (hook, body)


def wrap_untrusted(text: str | None) -> str | None:
    """Wrap raw competitor ad text/transcript in untrusted delimiters without filtering phrasing."""
    if not text or not str(text).strip():
        return None
    safe = _UNTRUSTED_TAG_RE.sub(
        lambda m: r"<\/untrusted_ad_content>" if m.group(1) else "&lt;untrusted_ad_content&gt;",
        str(text).strip(),
    )
    return f"{UNTRUSTED_OPEN}\n{safe}\n{UNTRUSTED_CLOSE}"


def find_cached_ad(ad_id: str, cache_dir: Path | None = None) -> dict | None:
    """Look up an ad in local cache JSON files (sorted newest first)."""
    directory = Path(cache_dir) if cache_dir else home_dir() / "cache"
    if not directory.is_dir():
        return None
    try:
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None

    ad_id = str(ad_id)
    for path in files:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        ads = payload.get("ads")
        if not isinstance(ads, list):
            continue
        for ad in ads:
            if not isinstance(ad, dict):
                continue
            collation = [str(x) for x in (ad.get("collation_ids") or [])]
            if str(ad.get("library_id") or "") == ad_id or ad_id in collation:
                return {
                    "ad_id": ad_id,
                    "media_type": ad.get("media_type"),
                    "video_url": ad.get("video_url"),
                    "body": ad.get("body") or "",
                    "headline": ad.get("headline"),
                    "cta": ad.get("cta"),
                    "advertiser": ad.get("advertiser"),
                    "started": ad.get("started"),
                }
    return None


def read_pack_context(pack_folder: str | Path, ad_id: str) -> dict | None:
    """Extract manifest flags and copy excerpt for ``ad_id`` from an existing analysis pack."""
    folder = Path(pack_folder)
    if not folder.is_dir():
        return None

    manifest: dict = {}
    manifest_path = folder / "manifest.json"
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
        except (OSError, ValueError):
            manifest = {}

    audit = manifest.get("audit") or {}
    excerpt: str | None = None
    copy_path = folder / "copy.md"
    if copy_path.is_file():
        try:
            text = copy_path.read_text(encoding="utf-8")
            pattern = re.compile(rf"^###\s+[^\n]*\bid\s+{re.escape(str(ad_id))}\b", re.MULTILINE)
            match = pattern.search(text)
            if match:
                rest = text[match.start():]
                end_match = re.search(r"\n(?:###|##)\s+", rest[4:])
                excerpt = (rest[: 4 + end_match.start()] if end_match else rest).strip()
        except OSError:
            excerpt = None

    return {
        "in_pack": str(ad_id) in {str(x) for x in (audit.get("ad_ids") or [])},
        "too_recent": str(ad_id) in {str(x) for x in (audit.get("too_recent_ids") or [])},
        "ended": str(ad_id) in {str(x) for x in (audit.get("ended_ids") or [])},
        "subject": manifest.get("subject"),
        "country": manifest.get("country"),
        "copy_excerpt": excerpt,
    }


class _SafeMetaRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block HTTP redirects that leave allowed Meta video CDN domains."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_video_url(newurl):
            raise ValueError("redirected video URL is not an allowed Meta CDN address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_meta_url(url: str, timeout: float):
    opener = urllib.request.build_opener(_SafeMetaRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return opener.open(request, timeout=timeout)


def download_video_checked(
    url: str,
    dest: Path,
    max_bytes: int = MAX_VIDEO_BYTES,
    timeout: float = DOWNLOAD_TIMEOUT,
    opener=None,
) -> Path:
    """Download a Meta CDN video in chunks while enforcing domain allowlist and byte cap."""
    if not is_allowed_video_url(url):
        raise ValueError("video URL is not an allowed Meta CDN address")

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    open_fn = opener or _open_meta_url
    total = 0
    with open_fn(url, timeout=timeout) as response:
        if hasattr(response, "geturl"):
            final_url = response.geturl()
            if final_url and not is_allowed_video_url(final_url):
                raise ValueError("final video URL is not an allowed Meta CDN address")
        with dest.open("wb") as handle:
            while True:
                chunk = response.read(65_536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"video exceeds {max_bytes // 1_000_000} MB limit")
                handle.write(chunk)
    if total == 0:
        raise ValueError("downloaded video is empty")
    return dest


def setup_whisper_model(model_size: str = DEFAULT_WHISPER_MODEL, *, model_loader=None) -> dict:
    """Pre-download a local Whisper model via CLI so MCP calls never time out."""
    model_size = validate_whisper_model(model_size)
    if model_loader is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return {
                "ok": False,
                "error": "not_installed",
                "model": model_size,
                "note": "Optional video extras are not installed. Run: pip install -e \".[video]\"",
            }
        model_loader = WhisperModel

    model_loader(model_size, device="cpu", compute_type="int8")
    return {"ok": True, "model": model_size, "note": f"Local Whisper model '{model_size}' is ready."}


def check_transcribe_ready(
    model_size: str = DEFAULT_WHISPER_MODEL,
    *,
    model_loader=None,
    av_opener=None,
) -> tuple[object | None, object | None, dict | None]:
    """Check ``.[video]`` packages and local Whisper cache before any download or browser launch."""
    model_size = validate_whisper_model(model_size)
    if model_loader is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return None, None, {
                "status": "not_installed",
                "has_audio": None,
                "language": None,
                "text": None,
                "segments": [],
                "note": "Optional local audio transcription is not installed. Run: pip install -e \".[video]\"",
            }
        model_loader = WhisperModel

    if av_opener is None:
        try:
            import av
        except ImportError:
            return None, None, {
                "status": "not_installed",
                "has_audio": None,
                "language": None,
                "text": None,
                "segments": [],
                "note": "Optional local audio transcription is not installed. Run: pip install -e \".[video]\"",
            }
        av_opener = av.open

    try:
        model = model_loader(model_size, device="cpu", compute_type="int8", local_files_only=True)
    except Exception:
        return None, None, {
            "status": "model_not_downloaded",
            "has_audio": None,
            "language": None,
            "text": None,
            "segments": [],
            "note": (
                f"Local Whisper model '{model_size}' is not downloaded yet. "
                f"Run once in your terminal: ad-library-insights video-setup --model {model_size}"
            ),
        }
    return model, av_opener, None


def transcribe_video_url(
    video_url: str,
    model_size: str = DEFAULT_WHISPER_MODEL,
    language: str | None = None,
    *,
    downloader=None,
    model_loader=None,
    av_opener=None,
    preloaded_model=None,
    preloaded_av=None,
) -> dict:
    """Optionally probe audio stream and transcribe speech using a pre-downloaded local Whisper model."""
    model_size = validate_whisper_model(model_size)
    if not is_allowed_video_url(video_url):
        raise ValueError("video URL is not an allowed Meta CDN address")

    if preloaded_model is not None and preloaded_av is not None:
        model, av_open = preloaded_model, preloaded_av
    else:
        model, av_open, early = check_transcribe_ready(
            model_size, model_loader=model_loader, av_opener=av_opener,
        )
        if early is not None:
            return early

    handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_path = Path(handle.name)
    handle.close()
    try:
        (downloader or download_video_checked)(video_url, tmp_path)
        container = av_open(str(tmp_path))
        try:
            has_audio = bool(getattr(container.streams, "audio", None))
        finally:
            if hasattr(container, "close"):
                container.close()
        if not has_audio:
            return {
                "status": "no_audio",
                "has_audio": False,
                "language": None,
                "text": "",
                "segments": [],
                "note": "This video has no audio track.",
            }

        clean_lang = (language or "").strip() or None
        raw_segments, info = model.transcribe(str(tmp_path), language=clean_lang, vad_filter=True)
        segments = []
        for seg in raw_segments:
            chunk = str(getattr(seg, "text", "") or "").strip()
            if chunk:
                segments.append({
                    "start": round(float(seg.start), 2),
                    "end": round(float(seg.end), 2),
                    "text": chunk,
                })
        full_text = " ".join(seg["text"] for seg in segments)
        return {
            "status": "ok",
            "has_audio": True,
            "language": getattr(info, "language", None),
            "text": full_text,
            "segments": segments,
            "note": None,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def _format_ad_copy(ad_meta: dict | None, pack_ctx: dict | None) -> str | None:
    if pack_ctx and pack_ctx.get("copy_excerpt"):
        return pack_ctx["copy_excerpt"]
    if not ad_meta:
        return None
    parts = []
    if ad_meta.get("advertiser"):
        parts.append(f"Advertiser: {ad_meta['advertiser']}")
    if ad_meta.get("started"):
        parts.append(f"Started: {ad_meta['started']}")
    if ad_meta.get("headline"):
        parts.append(f"Headline: {ad_meta['headline']}")
    if ad_meta.get("cta"):
        parts.append(f"CTA: {ad_meta['cta']}")
    if ad_meta.get("body"):
        parts.append(f"Body:\n{ad_meta['body']}")
    return "\n".join(parts) if parts else None


def _rel_path(path_str: str, base_dir: Path) -> str:
    try:
        return Path(path_str).relative_to(base_dir).as_posix()
    except ValueError:
        return Path(path_str).name


def _write_summary(out_dir: Path, payload: dict, ad_copy_raw: str | None, transcript_raw: str | None) -> Path:
    dims = f"{payload['width']}x{payload['height']}" if payload.get("width") and payload.get("height") else "unknown"
    ratio = payload.get("aspect_ratio") or "unknown"
    audio_line = (
        f"has_audio={payload['has_audio']}, status={payload['transcript_status']}"
        + (f", language={payload['transcript_language']}" if payload.get("transcript_language") else "")
        + (f" ({payload['transcript_note']})" if payload.get("transcript_note") else "")
    )
    lines = [
        f"# Video Inspection · Ad {payload['ad_id']}",
        "",
        f"- Duration: {payload.get('duration')}s",
        f"- Dimensions: {dims} (aspect ratio: {ratio})",
        f"- Audio: {audio_line}",
        "",
        "## Contact Sheets",
    ]
    for sheet in payload.get("contact_sheets") or []:
        rel = _rel_path(sheet["path"], out_dir)
        lines.append(f"- `{rel}` ({sheet['zone']}, {sheet['frames']} frames)")

    lines += ["", "## Frames"]
    for frame in payload.get("frames") or []:
        rel = _rel_path(frame["path"], out_dir)
        lines.append(f"- `{rel}` ({frame['zone']}, {format_timestamp(frame['timestamp'])})")

    pack_ctx = payload.get("pack_context")
    if pack_ctx:
        flags = []
        if pack_ctx.get("too_recent"):
            flags.append("too recent to judge")
        if pack_ctx.get("ended"):
            flags.append("no longer on air")
        lines += [
            "",
            "## Pack Context",
            f"- Subject: {pack_ctx.get('subject') or 'n/a'} ({pack_ctx.get('country') or 'n/a'})",
            f"- In pack: {pack_ctx.get('in_pack')}" + (f" ({'; '.join(flags)})" if flags else ""),
        ]

    wrapped_copy = wrap_untrusted(ad_copy_raw)
    if wrapped_copy:
        lines += ["", "## Ad Copy (untrusted ad data)", wrapped_copy]

    wrapped_tx = wrap_untrusted(transcript_raw)
    if wrapped_tx:
        lines += ["", "## Audio Transcript (untrusted ad data)", wrapped_tx]
    elif payload.get("transcript_note"):
        lines += ["", "## Audio Transcript", f"- {payload['transcript_note']}"]

    summary_path = out_dir / "summary.md"
    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return summary_path


def _format_transcript_block(segments: list[dict], plain_text: str | None) -> str | None:
    if segments:
        return "\n".join(
            f"[{format_timestamp(seg['start'])}-{format_timestamp(seg['end'])}] {seg['text']}"
            for seg in segments
        )
    return plain_text or None


def _build_response(meta: dict, out_dir: Path, summary_path: Path, pack_ctx: dict | None, from_cache: bool) -> dict:
    ad_copy_raw = meta.get("ad_copy_raw")
    segments = meta.get("transcript_segments") or []
    tx_raw = _format_transcript_block(segments, meta.get("transcript_text"))
    safe_pack = {k: v for k, v in pack_ctx.items() if k != "copy_excerpt"} if pack_ctx else None
    return {
        "ok": True,
        "ad_id": meta["ad_id"],
        "folder": str(out_dir),
        "summary_path": str(summary_path),
        "duration": meta.get("duration"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "aspect_ratio": meta.get("aspect_ratio"),
        "contact_sheets": meta.get("contact_sheets") or [],
        "frames": meta.get("frames") or [],
        "has_audio": meta.get("has_audio"),
        "transcript_status": meta.get("transcript_status"),
        "transcript_language": meta.get("transcript_language"),
        "transcript": wrap_untrusted(tx_raw),
        "transcript_segment_count": len(segments),
        "transcript_note": meta.get("transcript_note"),
        "ad_copy": wrap_untrusted(ad_copy_raw),
        "pack_context": safe_pack,
        "from_cache": from_cache,
    }


def _sheets_exist(meta: dict) -> bool:
    sheets = meta.get("contact_sheets") or []
    return bool(sheets) and all(Path(s.get("path", "")).is_file() for s in sheets)


async def _safe_fetch(fetch_fn, ad_id: str) -> dict:
    try:
        res = await fetch_fn(ad_id)
        return res if isinstance(res, dict) else {"found": False, "ad_id": ad_id}
    except Exception as exc:
        return {"found": False, "ad_id": ad_id, "media_type": None, "video_url": None, "body": "", "error": str(exc)}


async def inspect_video(
    ad_id: str,
    *,
    pack_folder: str | None = None,
    transcribe: bool = False,
    whisper_model: str = DEFAULT_WHISPER_MODEL,
    language: str | None = None,
    use_cache: bool = True,
    media_dir: Path | None = None,
    cache_dir: Path | None = None,
    fetcher=None,
    capturer=None,
    transcriber=None,
) -> dict:
    """Extract hook-first contact sheets, aspect ratio, and optional offline speech transcript for one ad."""
    ad_id = validate_ad_id(ad_id)
    if transcribe:
        whisper_model = validate_whisper_model(whisper_model)

    base_media = Path(media_dir) if media_dir else home_dir() / "media"
    out_dir = base_media / "video_inspect" / ad_id
    frames_dir = out_dir / "frames"
    meta_path = out_dir / "meta.json"
    summary_path = out_dir / "summary.md"

    fetch_fn = fetcher or browser.fetch_ad_video
    capture_fn = capturer or browser.capture_video_frames
    transcribe_fn = transcriber or transcribe_video_url

    pack_ctx = read_pack_context(pack_folder, ad_id) if pack_folder else None

    cached_meta: dict | None = None
    if use_cache and meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and _sheets_exist(loaded):
                cached_meta = loaded
        except (OSError, ValueError):
            cached_meta = None

    if cached_meta is not None:
        need_rewrite = not summary_path.is_file()
        if pack_ctx is not None:
            cached_meta["pack_context"] = pack_ctx
            if pack_ctx.get("copy_excerpt") and not cached_meta.get("ad_copy_raw"):
                cached_meta["ad_copy_raw"] = pack_ctx["copy_excerpt"]
            need_rewrite = True
        tx_done = cached_meta.get("transcript_status") in ("ok", "no_audio")
        if not transcribe or tx_done:
            if need_rewrite:
                summary_path = _write_summary(
                    out_dir, cached_meta, cached_meta.get("ad_copy_raw"),
                    _format_transcript_block(cached_meta.get("transcript_segments") or [], cached_meta.get("transcript_text")),
                )
                meta_path.write_text(json.dumps(cached_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return _build_response(cached_meta, out_dir, summary_path, pack_ctx, from_cache=True)

    cached_ad = find_cached_ad(ad_id, cache_dir)
    ad_meta = dict(cached_ad) if cached_ad else None
    active_url = (cached_ad or {}).get("video_url")

    capture: dict | None = None
    if cached_meta is not None:
        capture = {
            "duration": cached_meta.get("duration"),
            "width": cached_meta.get("width"),
            "height": cached_meta.get("height"),
            "frames": cached_meta.get("frames") or [],
            "contact_sheets": cached_meta.get("contact_sheets") or [],
        }
    else:
        if active_url and is_allowed_video_url(active_url):
            try:
                capture = await capture_fn(active_url, frames_dir, plan_timestamps, out_dir)
            except (RuntimeError, OSError):
                capture = None

        if capture is None:
            cap_err: str | None = None
            if fetcher is None and capturer is None:
                fresh, capture, cap_err = await browser.fetch_and_capture_ad_video(
                    ad_id, frames_dir, plan_timestamps, out_dir, url_validator=is_allowed_video_url,
                )
            else:
                fresh = await _safe_fetch(fetch_fn, ad_id)

            if fresh:
                merged = dict(ad_meta or {})
                for k, v in fresh.items():
                    if v is not None and v != "":
                        merged[k] = v
                ad_meta = merged
            media_type = (fresh or {}).get("media_type")
            fresh_url = (fresh or {}).get("video_url")
            if fresh and media_type in ("image", "carousel", "text") and not fresh_url:
                return {
                    "ok": False,
                    "outcome": "not_video",
                    "ad_id": ad_id,
                    "media_type": media_type,
                    "note": "This ad is not a video creative.",
                }
            if not fresh or not fresh.get("found") or not is_allowed_video_url(fresh_url):
                err_detail = (fresh or {}).get("error") or cap_err
                note = (
                    f"Could not retrieve video for ad {ad_id}: {err_detail}"
                    if err_detail
                    else f"Could not find a playable video matching ad_id {ad_id} on the Ad Library page."
                )
                return {
                    "ok": False,
                    "outcome": "unavailable",
                    "ad_id": ad_id,
                    "note": note,
                }
            active_url = fresh_url
            if capture is None:
                if cap_err is not None:
                    return {
                        "ok": False,
                        "outcome": "unavailable",
                        "ad_id": ad_id,
                        "note": f"Could not capture video frames: {cap_err}",
                    }
                try:
                    capture = await capture_fn(active_url, frames_dir, plan_timestamps, out_dir)
                except Exception as exc:
                    return {
                        "ok": False,
                        "outcome": "unavailable",
                        "ad_id": ad_id,
                        "note": f"Could not capture video frames: {exc}",
                    }

    tx = {
        "status": cached_meta.get("transcript_status", "not_requested") if cached_meta else "not_requested",
        "has_audio": cached_meta.get("has_audio") if cached_meta else None,
        "language": cached_meta.get("transcript_language") if cached_meta else None,
        "text": cached_meta.get("transcript_text") if cached_meta else None,
        "segments": cached_meta.get("transcript_segments", []) if cached_meta else [],
        "note": (
            cached_meta.get("transcript_note")
            if cached_meta
            else "Audio transcription not requested (pass transcribe=True to enable)."
        ),
    }

    if transcribe:
        ready_model, ready_av, early_tx = (
            check_transcribe_ready(whisper_model) if transcriber is None else (None, None, None)
        )
        if early_tx is not None:
            tx = early_tx
        else:
            def _run_tx(url: str) -> dict:
                if transcriber is not None:
                    return transcriber(url, whisper_model, language or None)
                return transcribe_video_url(
                    url, whisper_model, language or None,
                    preloaded_model=ready_model, preloaded_av=ready_av,
                )

            if not is_allowed_video_url(active_url):
                fresh = await _safe_fetch(fetch_fn, ad_id)
                if fresh:
                    merged = dict(ad_meta or {})
                    for k, v in fresh.items():
                        if v is not None and v != "":
                            merged[k] = v
                    ad_meta = merged
                active_url = (fresh or {}).get("video_url")

            if not is_allowed_video_url(active_url):
                tx = {
                    "status": "unavailable",
                    "has_audio": None,
                    "language": None,
                    "text": None,
                    "segments": [],
                    "note": "Could not retrieve a playable Meta video URL for audio transcription.",
                }
            else:
                try:
                    tx = await asyncio.to_thread(_run_tx, active_url)
                except (OSError, urllib.error.URLError, ValueError, RuntimeError) as first_exc:
                    # Cached signed CDN URL may have expired between visual capture and transcription.
                    fresh = await _safe_fetch(fetch_fn, ad_id)
                    fresh_url = (fresh or {}).get("video_url")
                    if is_allowed_video_url(fresh_url) and fresh_url != active_url:
                        try:
                            tx = await asyncio.to_thread(_run_tx, fresh_url)
                        except (OSError, urllib.error.URLError, ValueError, RuntimeError) as retry_exc:
                            tx = {
                                "status": "error",
                                "has_audio": None,
                                "language": None,
                                "text": None,
                                "segments": [],
                                "note": f"Audio transcription failed: {retry_exc}",
                            }
                    else:
                        detail = fresh.get("error") or first_exc
                        tx = {
                            "status": "error",
                            "has_audio": None,
                            "language": None,
                            "text": None,
                            "segments": [],
                            "note": f"Audio transcription failed: {detail}",
                        }

    ad_copy_raw = _format_ad_copy(ad_meta, pack_ctx) or (cached_meta or {}).get("ad_copy_raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    new_meta = {
        "ad_id": ad_id,
        "duration": capture.get("duration"),
        "width": capture.get("width"),
        "height": capture.get("height"),
        "aspect_ratio": format_aspect_ratio(capture.get("width"), capture.get("height")),
        "contact_sheets": capture.get("contact_sheets") or [],
        "frames": capture.get("frames") or [],
        "has_audio": tx.get("has_audio"),
        "transcript_status": tx.get("status"),
        "transcript_language": tx.get("language"),
        "transcript_text": tx.get("text"),
        "transcript_segments": tx.get("segments") or [],
        "transcript_note": tx.get("note"),
        "ad_copy_raw": ad_copy_raw,
        "pack_context": pack_ctx,
    }
    tx_raw = _format_transcript_block(new_meta["transcript_segments"], new_meta["transcript_text"])
    summary_path = _write_summary(out_dir, new_meta, ad_copy_raw, tx_raw)
    meta_path.write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return _build_response(new_meta, out_dir, summary_path, pack_ctx, from_cache=False)
