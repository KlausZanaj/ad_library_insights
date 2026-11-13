"""The local web app: a small server on 127.0.0.1 and one page in the browser.

Everything runs on the user's computer. The server wraps the same research pipeline
the MCP tools use; searches run in the background one at a time and the page polls
for progress. No model is called from here: the Analysis and Plan levels end in a
text the user gives to their own assistant.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .. import __version__, briefs, consumption, details, media, project, service
from ..client import AdLibraryClient, normalise_country
from ..storage import DiskCache, Throttle

STATIC = Path(__file__).parent / "static"
TABLE_THUMBNAILS = 60          # thumbnails kept for the ads listed in the table
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


class Workspace:
    """Holds the client, the jobs and the one-at-a-time rule for page requests."""

    def __init__(self, client: AdLibraryClient | None = None, home: Path | None = None):
        self.client = client or AdLibraryClient(cache=DiskCache(), throttle=Throttle(), sleep=self._sleep)
        self.home = home
        self.jobs: dict[str, Job] = {}
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

    async def _run(self, job: Job) -> None:
        params = job.params
        async with self._lock:
            self._current = job
            try:
                job.phase = "list"
                if params["mode"] == "company":
                    result = await service.research_company(self.client, params["country"],
                                                            page_id=params["page_id"])
                else:
                    result = await service.research(self.client, params["query"], params["country"],
                                                    scroll_rounds=KEYWORD_SCROLLS)
                if result.get("ads"):
                    plan = service.estimate_deep(result, params["deep"], params["frames"])
                    job.phase = "details"
                    job.detail = {"done": 0, "total": plan["ads"], "eta_seconds": plan["seconds"]}

                    def progress(event: dict) -> None:
                        if job.phase == "details":
                            job.detail = {"done": event["done"], "total": event["total"],
                                          "eta_seconds": event["eta_seconds"]}

                    await service.deepen(self.client, result, params["deep"], params["frames"], progress)
                    job.phase, job.detail = "media", {}
                    await asyncio.to_thread(media.save_ad_media, result["ads"][:TABLE_THUMBNAILS],
                                            self.client.media)
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
        query = request.query_params
        try:
            ads = int(query.get("ads", 10))
            found = consumption.estimate(query.get("level", "data"), ads, query.get("frames") == "1")
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        found["seconds"] = details.estimate_seconds(ads, min(ads, consumption.ADS_WITH_FRAMES)
                                                    if query.get("frames") == "1" else 0)
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
            return JSONResponse({"errors": errors}, status_code=400)
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
            }
            if params["mode"] not in ("keyword", "company"):
                raise ValueError("mode must be keyword or company")
            if params["level"] not in consumption.LEVELS:
                raise ValueError("unknown level")
            if params["mode"] == "keyword" and not params["query"]:
                raise ValueError("query must not be empty")
            if params["mode"] == "company" and not params["page_id"].isdigit():
                raise ValueError("page_id must be the numeric id of an advertiser page")
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

    async def brief(self, request: Request) -> Response:
        body = await request.json()
        job = self.jobs.get(str(body.get("job_id")))
        if not job or not job.raw or not job.raw.get("ads"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        level = body.get("level", "analysis")
        card = project.load(self.home)
        if level == "plan" and not card:
            return JSONResponse({"error": "project_required"}, status_code=409)
        try:
            made = briefs.compose(level, job.raw, int(body.get("ads", 10)), bool(body.get("frames")),
                                  card, body.get("lang", "it"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(made)


def create_app(client: AdLibraryClient | None = None, home: Path | None = None) -> Starlette:
    """The ASGI app. ``client`` and ``home`` are injectable for offline tests."""
    space = Workspace(client, home)
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
