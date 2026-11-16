"""The local web app: a small server on 127.0.0.1 and one page in the browser.

Everything runs on the user's computer. The server wraps the same research pipeline
the MCP tools use; searches run in the background one at a time and the page polls
for progress. No model is called from here: the Analysis and Plan levels end in a
text the user gives to their own assistant.
"""
from __future__ import annotations

import asyncio
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .. import __version__, briefs, compare, consumption, details, history, link, media, project, rating, service
from ..client import AdLibraryClient, normalise_country
from ..storage import DiskCache, Throttle

STATIC = Path(__file__).parent / "static"
TABLE_THUMBNAILS = 150         # thumbnails kept for the ads listed in the table
KEYWORD_SCROLLS = 8
_SAFE_NAME = re.compile(r"^[\w.-]+$")


@dataclass
class Job:
    """One search running in the background."""

    id: str
    params: dict
    status: str = "running"              # running | done | error
    phase: str = "queued"                # queued | waiting | list | details | media
    detail: dict = field(default_factory=dict)
    result: dict | None = None           # what the page shows
    raw: dict | None = None              # the pipeline result, with local file paths
    error: str | None = None

    def view(self) -> dict:
        return {"id": self.id, "status": self.status, "phase": self.phase, "detail": self.detail,
                "params": self.params, "error": self.error, "result": self.result}


def _media_url(path: str | None) -> str | None:
    return f"/media/{Path(path).name}" if path else None


def present(result: dict, params: dict) -> dict:
    """The research result as the page needs it: local pictures as URLs, plus the request."""
    shown = dict(result)
    shown["ads"] = []
    for ad in result.get("ads", []):
        row = {k: v for k, v in ad.items() if k not in ("image_url", "logo_url", "video_url")}
        row["thumbnail"] = _media_url(ad.get("thumbnail_path"))
        row["logo"] = _media_url(ad.get("logo_path"))
        row["frames"] = [_media_url(path) for path in ad.get("frames") or []]
        shown["ads"].append(row)
    if result.get("page"):
        shown["page"] = {**result["page"], "logo": _media_url(result["page"].get("logo_path"))}
    shown["request"] = params
    return shown


def open_folder(folder: Path) -> None:
    """Show a folder in the file manager of the user's computer."""
    import os
    import subprocess
    import sys

    if sys.platform.startswith("win"):
        os.startfile(str(folder))  # noqa: S606 - a folder the app itself wrote
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])


class Workspace:
    """Holds the client, the jobs and the one-at-a-time rule for page requests."""

    def __init__(self, client: AdLibraryClient | None = None, home: Path | None = None,
                 connection: link.Settings | None = None):
        self.client = client or AdLibraryClient(cache=DiskCache(), throttle=Throttle(), sleep=self._sleep)
        self.home = home
        self.connection = connection or link.Settings()
        self._used_tokens: set[str] = set()          # a confirmation token works once
        self._connecting = threading.Lock()
        self.history = history.History(Path(home) / "snapshots" if home else None)
        self.jobs: dict[str, Job] = {}
        self.frame_folders: dict[str, Path] = {}     # key given to the page -> stills folder of a pack
        self.opener = open_folder
        self._lock = asyncio.Lock()
        self._current: Job | None = None

    async def _sleep(self, seconds: float) -> None:
        """Pauses asked by the client; long ones are shown as "waiting" on the page."""
        job = self._current
        if job is None or seconds < 3:
            await asyncio.sleep(seconds)
            return
        before = (job.phase, job.detail)
        job.phase, job.detail = "waiting", {"seconds": round(seconds)}
        try:
            await asyncio.sleep(seconds)
        finally:
            job.phase, job.detail = before

    # --- jobs -------------------------------------------------------------------------

    def start(self, params: dict) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], params=params)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job))   # keep a reference so it is not collected
        return job

    async def _collect(self, job: Job, params: dict, page_id: str | None = None,
                       side: int | None = None) -> dict:
        """One search with its reach reading, thumbnails and saved snapshot."""
        mark = {"side": side} if side else {}
        job.phase, job.detail = "list", dict(mark)
        use_cache = not params.get("fresh")
        if page_id:
            result = await service.research_company(self.client, params["country"], page_id=page_id,
                                                    use_cache=use_cache)
        else:
            result = await service.research(self.client, params["query"], params["country"],
                                            scroll_rounds=KEYWORD_SCROLLS, use_cache=use_cache)
        if result.get("ads"):
            plan = service.estimate_deep(result, params["deep"], params["frames"])
            job.phase = "details"
            job.detail = {**mark, "done": 0, "total": plan["ads"], "eta_seconds": plan["seconds"]}

            def progress(event: dict) -> None:
                if job.phase == "details":
                    job.detail = {**mark, "done": event["done"], "total": event["total"],
                                  "eta_seconds": event["eta_seconds"]}

            await service.deepen(self.client, result, params["deep"], params["frames"], progress, use_cache)
            job.phase, job.detail = "media", dict(mark)
            await asyncio.to_thread(media.save_ad_media, result["ads"][:TABLE_THUMBNAILS], self.client.media)
            # every search is remembered, so the next one can tell what changed
            result["changes"] = history.summary(self.history.record(result))
        return result

    async def _run(self, job: Job) -> None:
        params = job.params
        async with self._lock:
            self._current = job
            try:
                if params["mode"] == "compare":
                    first = await self._collect(job, params, params["page_id"], side=1)
                    second = await self._collect(job, params, params["page_id_b"], side=2)
                    both = bool(first.get("ads") and second.get("ads"))
                    job.result = {"mode": "compare", "country": params["country"], "request": params,
                                  "sides": [present(first, params), present(second, params)],
                                  "comparison": compare.compare(first, second) if both else None}
                else:
                    result = await self._collect(
                        job, params, params["page_id"] if params["mode"] == "company" else None)
                    job.raw, job.result = result, present(result, params)
                job.status = "done"
            except Exception as exc:  # shown to the user instead of a dead spinner
                job.status, job.error = "error", f"{type(exc).__name__}: {exc}"
            finally:
                self._current = None

    # --- request handlers -------------------------------------------------------------

    async def index(self, request: Request) -> Response:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    async def media_file(self, request: Request) -> Response:
        name = request.path_params["name"]
        path = self.client.media.directory / name
        if not _SAFE_NAME.match(name) or not path.is_file():
            return JSONResponse({"error": "not_found"}, status_code=404)
        return FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    async def state(self, request: Request) -> Response:
        return JSONResponse({"version": __version__, "project": project.load(self.home),
                             "deep_choices": list(consumption.DEEP_CHOICES)})

    async def estimate(self, request: Request) -> Response:
        """Usage before a search starts. ``ads`` is the number of concepts asked for.

        The ads that will really be opened are known only once the list is loaded, so
        the time is given for the ceiling: at most two ads opened per concept asked.
        """
        query = request.query_params
        frames = query.get("frames") == "1"
        try:
            concepts = max(0, int(query.get("ads", 10)))
            found = consumption.estimate(query.get("level", "data"), concepts, frames)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        ceiling = rating.read_ceiling(concepts)
        found.update(concepts=concepts, ceiling=ceiling, seconds=details.estimate_seconds(
            ceiling, min(concepts, consumption.ADS_WITH_FRAMES) if frames else 0))
        return JSONResponse(found)

    async def pages(self, request: Request) -> Response:
        name = (request.query_params.get("name") or "").strip()
        try:
            country = normalise_country(request.query_params.get("country", ""))
            if not name:
                raise ValueError("name must not be empty")
            async with self._lock:
                found = await service.find_pages(self.client, name, country)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        logos = await asyncio.to_thread(
            lambda: [self.client.media.save(p.get("logo_url"), f"page_{p['page_id']}_logo")
                     for p in found["pages"][:12]])
        for page, logo in zip(found["pages"], logos):
            page["logo"] = _media_url(logo)
        for page in found["pages"]:
            page.pop("logo_url", None)
        return JSONResponse(found)

    async def get_project(self, request: Request) -> Response:
        return JSONResponse({"project": project.load(self.home)})

    async def put_project(self, request: Request) -> Response:
        card, errors = project.save(await request.json(), self.home)
        if errors:
            return JSONResponse({"errors": errors, "project": None})   # 200: a refused card is not a failed request
        return JSONResponse({"project": card})

    async def create_job(self, request: Request) -> Response:
        body = await request.json()
        try:
            params = {
                "mode": body.get("mode"),
                "country": normalise_country(body.get("country", "")),
                "level": body.get("level", "data"),
                "deep": max(0, min(int(body.get("deep", 10)), max(consumption.DEEP_CHOICES))),
                "frames": bool(body.get("frames")),
                "query": (body.get("query") or "").strip(),
                "page_id": str(body.get("page_id") or "").strip(),
                "page_id_b": str(body.get("page_id_b") or "").strip(),
                "fresh": bool(body.get("fresh")),      # skip the cache: used to look for changes
            }
            if params["mode"] not in ("keyword", "company", "compare"):
                raise ValueError("mode must be keyword, company or compare")
            if params["level"] not in consumption.LEVELS:
                raise ValueError("unknown level")
            if params["mode"] == "keyword" and not params["query"]:
                raise ValueError("query must not be empty")
            if params["mode"] in ("company", "compare") and not params["page_id"].isdigit():
                raise ValueError("page_id must be the numeric id of an advertiser page")
            if params["mode"] == "compare":
                if not params["page_id_b"].isdigit() or params["page_id_b"] == params["page_id"]:
                    raise ValueError("page_id_b must be the numeric id of a second, different page")
                params["level"] = "data"            # a comparison is code only
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if params["level"] == "plan" and not project.load(self.home):
            return JSONResponse({"error": "project_required"}, status_code=409)
        if params["level"] == "data":
            params["frames"] = False
        return JSONResponse(self.start(params).view(), status_code=202)

    async def get_job(self, request: Request) -> Response:
        job = self.jobs.get(request.path_params["job_id"])
        if not job:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(job.view())

    async def saved_searches(self, request: Request) -> Response:
        return JSONResponse({"subjects": self.history.subjects()})

    async def demo(self, request: Request) -> Response:
        """Load an offline sample search so a first-time visitor can explore the table and KPIs immediately."""
        import json
        from datetime import date
        from .. import signals
        from ..client import FetchResult

        level = request.query_params.get("level") or "analysis"
        if level not in consumption.LEVELS:
            level = "analysis"
        root = Path(__file__).resolve().parents[3]
        fx = root / "tests" / "fixtures" / "rating_kingshot_it.json"
        det_fx = root / "tests" / "fixtures" / "ad_details_eu_many_countries.json"
        if fx.is_file() and det_fx.is_file():
            data = json.loads(fx.read_text(encoding="utf-8"))
            parsed_det = details.parse_details(json.loads(det_fx.read_text(encoding="utf-8")))
            fetch = FetchResult(url="https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=IT&q=Kingshot",
                                outcome="ok", ads=data["cards"], total_count=216, source="structured")
            result = service.assemble(fetch, "Kingshot", "IT", as_of=date.fromisoformat(data["as_of"]))
            for item in result["ads"]:
                found = data["reach"].get(item["library_id"])
                if found:
                    item["reach"] = {**found, "regions": parsed_det["reach"].get("regions", [])}
                    item["audience"] = parsed_det["audience"]
                for other in item["variant_ids"]:
                    if other in data["reach"]:
                        item.setdefault("card_reach", {})[other] = data["reach"][other]
            signals.annotate(result["ads"], library_total=216)
            signals.refresh(result["signals"], result["ads"], "IT")
            params = {"mode": "company", "country": "IT", "level": level, "deep": 10, "frames": False,
                      "query": "Kingshot", "page_id": "100089123456", "fresh": False}
            result.update(
                mode="company",
                ads_parsed=212,
                from_cache=True,
                page={"name": "Kingshot", "category": "Game Publisher", "followers": 2596792},
                changes={"available": False},
                deep={"requested": 10, "read": 14, "concepts": 12, "with_reach": 12,
                      "ceiling": 20, "capped": False, "left_out": 0},
            )
            raw = json.loads(json.dumps(result, default=str))
            shown = present(raw, params)
            shown["demo"] = True
            job = Job(id="demo", params=params, status="done", phase="media", result=shown, raw=raw)
            self.jobs["demo"] = job
            return JSONResponse(job.view())
        return JSONResponse({"error": "not_found"}, status_code=404)

    async def changes(self, request: Request) -> Response:
        found = self.history.changes(request.query_params.get("key", ""))
        for group in ("new", "stopped", "changed"):
            for ad in found.get(group, []):
                ad["thumbnail"] = _media_url(ad.pop("thumbnail_path", None))
        return JSONResponse(found)

    async def brief(self, request: Request) -> Response:
        body = await request.json()
        job = self.jobs.get(str(body.get("job_id")))
        if not job or not job.raw or not job.raw.get("ads"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        level = body.get("level", "analysis")
        card = project.load(self.home)
        if level == "plan" and not card:
            return JSONResponse({"error": "project_required"}, status_code=409)
        frames = bool(body.get("frames")) and bool(job.params.get("frames"))    # only if they were collected
        try:
            made = briefs.prepare(level, job.raw, int(body.get("ads", 10)), frames, card,
                                  body.get("lang", "it"),
                                  Path(self.home) / "packs" if self.home else None)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        deep = job.raw.get("deep") or {}
        read = deep["concepts"] if "concepts" in deep else (
            len([ad for ad in job.raw["ads"] if "reach" in ad]) or job.params["deep"])
        made["collected"] = {"ads": read, "frames": bool(job.params.get("frames"))}
        # the page names the pack by its folder only and opens the stills through a key
        made["folder_name"] = Path(made["folder"]).name
        made["frames_key"] = None
        if made.get("frames_folder"):
            made["frames_key"] = uuid.uuid4().hex
            self.frame_folders[made["frames_key"]] = Path(made["frames_folder"])
        return JSONResponse(made)

    async def open_frames(self, request: Request) -> Response:
        """Open the stills folder of a pack this app wrote; nothing else can be opened."""
        origin = request.headers.get("origin")
        if origin is not None:
            host = request.headers.get("host", "")
            port = host.rsplit(":", 1)[1] if ":" in host else ""
            own = {f"http://{name}" + (f":{port}" if port else "") for name in ("127.0.0.1", "localhost")}
            if origin not in own:
                return JSONResponse({"error": "forbidden_origin"}, status_code=403)
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return JSONResponse({"error": "bad_request"}, status_code=400)
        folder = self.frame_folders.get(str(body.get("key") or ""))
        if folder is None or not folder.is_dir():
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            self.opener(folder)
        except OSError as exc:
            return JSONResponse({"error": "open_failed", "detail": type(exc).__name__}, status_code=500)
        return JSONResponse({"opened": True, "pictures": sum(1 for p in folder.iterdir() if p.is_file())})


    # --- connection to Claude Code ----------------------------------------------------

    async def link_status(self, request: Request) -> Response:
        """What is already in place; no command is run here."""
        return JSONResponse(link.status(self.connection))

    async def link_mcp(self, request: Request) -> Response:
        """The slow check (``claude mcp list``), asked by the page in the background."""
        return JSONResponse(await asyncio.to_thread(link.mcp_status, self.connection))

    async def link_connect(self, request: Request) -> Response:
        """Register the server and copy the skills. Only the page itself may ask, once per token."""
        if not _own_page(request):
            return JSONResponse({"error": "forbidden_origin"}, status_code=403)
        if not (request.headers.get("content-type") or "").split(";")[0].strip() == "application/json":
            return JSONResponse({"error": "bad_request"}, status_code=400)
        try:
            body = await request.json()
        except ValueError:
            body = None
        token = request.headers.get("x-link-token", "")
        if not isinstance(body, dict) or not _TOKEN.match(token) or body.get("token") != token:
            return JSONResponse({"error": "bad_token"}, status_code=403)
        if token in self._used_tokens:
            return JSONResponse({"error": "bad_token"}, status_code=403)
        self._used_tokens.add(token)
        if not self._connecting.acquire(blocking=False):
            return JSONResponse({"error": "busy"}, status_code=409)
        try:
            done = await asyncio.to_thread(link.connect, self.connection, bool(body.get("overwrite_skills")))
        finally:
            self._connecting.release()
        return JSONResponse(done, status_code=200 if done.get("ok") else 500)


_TOKEN = re.compile(r"^[0-9a-f]{32,128}$")


def _own_page(request: Request) -> bool:
    """True only for a request sent by this app's own page on 127.0.0.1 (Origin and Host both say so)."""
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    name, _, port = host.partition(":")
    if name != "127.0.0.1":
        return False
    return origin == "http://127.0.0.1" + (f":{port}" if port else "")


def create_app(client: AdLibraryClient | None = None, home: Path | None = None,
               connection: link.Settings | None = None) -> Starlette:
    """The ASGI app. ``client``, ``home`` and ``connection`` are injectable for offline tests."""
    space = Workspace(client, home, connection)
    app = Starlette(routes=[
        Route("/", space.index),
        Route("/media/{name}", space.media_file),
        Route("/api/state", space.state),
        Route("/api/estimate", space.estimate),
        Route("/api/pages", space.pages),
        Route("/api/project", space.get_project, methods=["GET"]),
        Route("/api/project", space.put_project, methods=["PUT"]),
        Route("/api/jobs", space.create_job, methods=["POST"]),
        Route("/api/jobs/{job_id}", space.get_job),
        Route("/api/brief", space.brief, methods=["POST"]),
        Route("/api/frames/open", space.open_frames, methods=["POST"]),
        Route("/api/link/status", space.link_status),
        Route("/api/link/mcp", space.link_mcp),
        Route("/api/link/connect", space.link_connect, methods=["POST"]),
        Route("/api/history", space.saved_searches),
        Route("/api/history/changes", space.changes),
        Route("/api/demo", space.demo, methods=["GET", "POST"]),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ])
    app.state.workspace = space
    return app


def serve(port: int = 8765, open_browser: bool = True) -> None:
    """Run the app on 127.0.0.1 and open it in the default browser."""
    import socket
    import threading
    import webbrowser

    import uvicorn

    for candidate in range(port, port + 20):          # first free port from the preferred one
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", candidate)) != 0:
                port = candidate
                break
    url = f"http://127.0.0.1:{port}/"
    print(f"Ad Library Insights: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
