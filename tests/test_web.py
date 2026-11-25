"""The local app, offline: API, consumption estimate, project card, brief, page texts."""
import json
import re
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ad_library_insights import ai_runner, briefs, consumption, project, video
from ad_library_insights.web.app import STATIC, create_app
from test_company import PAGE_ID, Studio

CARD = {"product": "Standing desk", "price": "349", "product_cost": "120", "market": "de",
        "goal": "30 orders a day", "main_problem": "High cost per purchase"}


@pytest.fixture
def app(tmp_path):
    studio = Studio(tmp_path)
    with TestClient(create_app(studio.client, home=tmp_path / "home")) as client:
        yield client, studio


def run_job(client, **body):
    job = client.post("/api/jobs", json=body).json()
    for _ in range(200):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# --- consumption ----------------------------------------------------------------------

def test_data_level_uses_nothing():
    found = consumption.estimate("data", 50, frames=True)
    assert found == {"level": "data", "uses_assistant": False, "ads": 50, "images": 0,
                     "tokens": 0, "band": "none"}


def test_estimate_grows_with_ads_frames_and_level():
    small = consumption.estimate("analysis", 10)
    assert small["band"] == "low" and small["images"] == 0
    with_frames = consumption.estimate("analysis", 10, frames=True)
    assert with_frames["images"] == 30 and with_frames["tokens"] > small["tokens"]
    assert consumption.estimate("analysis", 50, frames=True)["images"] == 30     # best ten ads only
    assert consumption.estimate("analysis", 20)["tokens"] > small["tokens"]
    plan = consumption.estimate("plan", 10)
    assert plan["tokens"] > small["tokens"]                                       # more specialists re-read
    assert consumption.estimate("plan", 50, frames=True)["band"] == "high"
    with pytest.raises(ValueError):
        consumption.estimate("everything", 10)


def test_estimate_endpoint_follows_the_choices(app):
    client, _ = app
    low = client.get("/api/estimate?level=analysis&ads=10&frames=0").json()
    high = client.get("/api/estimate?level=plan&ads=50&frames=1").json()
    assert low["band"] == "low" and high["band"] == "high" and high["seconds"] > low["seconds"]
    assert client.get("/api/estimate?level=nope").status_code == 400


def test_estimate_counts_concepts_and_the_ceiling_of_ads_opened(app):
    client, _ = app
    found = client.get("/api/estimate?level=analysis&ads=20&frames=1").json()
    assert found["concepts"] == 20 and found["ceiling"] == 40           # two ads opened per concept asked
    assert found["images"] == 30 and found["tokens"] > 0 and found["band"] in ("low", "medium", "high")
    assert "percent" not in json.dumps(found)                            # an estimate, no share of a limit


# --- project card ---------------------------------------------------------------------

def test_project_card_is_validated_and_kept_on_disk(tmp_path):
    assert project.load(tmp_path) is None
    card, errors = project.save({**CARD, "price": "349,90"}, tmp_path)
    assert errors == {} and card["price"] == 349.9 and card["market"] == "DE"
    assert project.load(tmp_path)["product"] == "Standing desk"


def test_project_card_errors_name_the_field(tmp_path):
    _, errors = project.save({"product": " ", "price": "abc", "product_cost": "-1", "market": "Germany"}, tmp_path)
    assert errors == {"product": "required", "goal": "required", "main_problem": "required",
                      "price": "number", "product_cost": "positive", "market": "country"}
    _, errors = project.save({**CARD, "product_cost": "400"}, tmp_path)
    assert errors == {"product_cost": "above_price"}
    assert project.load(tmp_path) is None                      # nothing written on errors


def test_project_endpoints(app):
    client, _ = app
    assert client.get("/api/state").json()["project"] is None
    refused = client.put("/api/project", json={"product": "x"})
    assert refused.status_code == 200 and refused.json()["project"] is None and "price" in refused.json()["errors"]
    saved = client.put("/api/project", json=CARD).json()["project"]
    assert saved["price"] == 349.0
    assert client.get("/api/project").json()["project"]["market"] == "DE"


def test_precheck_endpoint_computes_real_margin_italy_fee_and_cpc(app):
    client, _ = app
    assert client.post("/api/precheck", content=b"not json").status_code == 400
    assert client.post("/api/precheck", json={"price": 0, "product_cost": 10}).status_code == 400
    assert client.post("/api/precheck", json={"price": 40, "product_cost": 35, "shipping_cost": 10}).status_code == 400

    res = client.post("/api/precheck", json={
        "price": 60, "product_cost": 15, "shipping_cost": 5,
        "payment_fee_pct": 2.9, "payment_fee_fixed": 0.25, "market": "IT",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body["ad_fee_pct"] == 3.0
    assert body["net_margin"] == 38.01
    assert body["cpa_ads"] == round(38.01 / 1.03, 2)
    assert [s["cvr_pct"] for s in body["cpc_scenarios"]] == [1, 2, 3]
    assert body["risk"]["max_loss_billed"] > body["risk"]["round_spend"]
    assert body["stop_rule"]["p_zero_3x"] == 0.0498


# --- searches -------------------------------------------------------------------------

def test_page_and_static_files_are_served(app):
    client, _ = app
    assert "Ad Library Insights" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_page_lookup_returns_candidates_with_local_logos(app):
    client, studio = app
    found = client.get("/api/pages?name=Zalando&country=it").json()
    assert len(found["pages"]) == 15 and found["suggested_page_id"] == "365604620536"
    assert found["pages"][0]["logo"].startswith("/media/page_") and "logo_url" not in found["pages"][0]
    assert client.get(found["pages"][0]["logo"]).content.startswith(b"\xff\xd8")
    assert client.get("/api/pages?name=&country=IT").status_code == 400


def test_company_job_returns_ranked_ads_with_local_pictures(app):
    client, _ = app
    job = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="data", deep=2)
    assert job["status"] == "done" and job["error"] is None
    result = job["result"]
    assert result["mode"] == "company" and result["page"]["name"] == "Kingshot"
    assert result["page"]["logo"].startswith("/media/")
    assert result["signals"]["active_ads"] == 194 and result["request"]["level"] == "data"
    top = result["ads"][0]
    assert top["reach"]["eu_total"] == 7398228 and top["thumbnail"].startswith("/media/ad_")
    assert sum(top["score_points"].values()) == pytest.approx(top["score"], abs=0.11)
    assert top["longevity_parts"]["days"] + top["longevity_parts"]["reuse"] == pytest.approx(top["longevity_score"], abs=0.11)
    assert top["reliability"] in ("high", "medium") and top["verdict"]
    assert "image_url" not in top and "reach" not in result["ads"][-1]
    assert result["ads"][-1]["thumbnail"]                       # thumbnails cover the whole table
    assert client.get(top["thumbnail"]).status_code == 200


def test_keyword_job_and_bad_requests(app):
    client, _ = app
    job = run_job(client, mode="keyword", query="desk", country="DE", level="data", deep=10)
    assert job["status"] == "done" and job["result"]["ads"]
    for body in ({"mode": "keyword", "query": "", "country": "DE"},
                 {"mode": "company", "page_id": "kingshot", "country": "IT"},
                 {"mode": "other", "country": "IT"},
                 {"mode": "keyword", "query": "desk", "country": "Italy"},
                 {"mode": "keyword", "query": "desk", "country": "IT", "level": "magic"}):
        assert client.post("/api/jobs", json=body).status_code == 400
    assert client.get("/api/jobs/missing").status_code == 404


def test_media_route_only_serves_saved_pictures(app):
    client, _ = app
    assert client.get("/media/nothing.jpg").status_code == 404
    assert client.get("/media/..%2Fthrottle.json").status_code == 404


def test_durata_endpoint_validates_inputs_and_runs_job(app):
    client, _ = app
    assert client.post("/api/durata", content=b"not json").status_code == 400
    for body in (
        {"page_id": "kingshot", "country": "IT", "window_days": 90},
        {"page_id": PAGE_ID, "country": "Italy", "window_days": 90},
        {"page_id": PAGE_ID, "country": "IT", "window_days": 15},
    ):
        assert client.post("/api/durata", json=body).status_code == 400

    res = client.post("/api/durata", json={"page_id": PAGE_ID, "country": "IT", "window_days": 90})
    assert res.status_code == 202
    job = res.json()
    for _ in range(200):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "done" and job["error"] is None
    assert job["result"]["durata"]["unit"] == "concept"
    assert job["result"]["durata"]["window_days"] == 90


def test_ritmo_history_endpoint_and_changes_include_ritmo(app):
    client, studio = app
    missing = client.get("/api/history/ritmo", params={"key": f"company:IT:{PAGE_ID}"}).json()
    assert missing["available"] is False and missing["reason"] == "no_snapshots"

    first = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="data", deep=1)
    assert "ritmo" in first["result"] and first["result"]["ritmo"]["unit"] == "concept"
    key = first["result"]["changes"]["key"]
    hist_one = client.get("/api/history/ritmo", params={"key": key}).json()
    assert hist_one["snapshots"] == 1 and hist_one["reason"] == "partial_list"

    studio.now += 86_400
    second = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="data", deep=1, fresh=True)
    assert second["result"]["changes"]["available"] is True
    changes_payload = client.get("/api/history/changes", params={"key": key}).json()
    assert changes_payload["available"] is True and "ritmo" in changes_payload
    assert changes_payload["ritmo"]["snapshots"] == 2


def test_jobs_and_compare_include_struttura_anomalie_and_pianka(app):
    client, _ = app
    comp = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="data", deep=2)["result"]
    assert "struttura" in comp and comp["struttura"]["sample_scope"] == "company"
    assert "anomalie" in comp and comp["anomalie"]["sample_scope"] == "company"

    kw = run_job(client, mode="keyword", query="desk", country="DE", level="data", deep=1)["result"]
    assert "struttura" in kw and kw["struttura"]["sample_scope"] == "keyword_sample"
    assert "anomalie" in kw and kw["anomalie"]["sample_scope"] == "keyword_sample"

    cmp_res = run_job(client, mode="compare", page_id=PAGE_ID, page_id_b="365604620536", country="IT", level="data", deep=1)["result"]
    assert "audience_overlap" in cmp_res["comparison"]
    assert cmp_res["comparison"]["audience_overlap"]["ads_a"] >= 0


# --- levels ---------------------------------------------------------------------------

def test_plan_needs_the_project_card_first(app):
    client, _ = app
    body = {"mode": "company", "page_id": PAGE_ID, "country": "IT", "level": "plan", "deep": 2}
    refused = client.post("/api/jobs", json=body)
    assert refused.status_code == 409 and refused.json()["error"] == "project_required"
    client.put("/api/project", json=CARD)
    job = run_job(client, **body)
    made = client.post("/api/brief", json={"job_id": job["id"], "level": "plan", "ads": 2, "lang": "en"}).json()
    assert "head of marketing" in made["text"] and "Standing desk" in made["text"]
    assert "may cost in ads: 229" in made["text"] and "up to 572.5" in made["text"]
    assert Path(made["files"]["project"]).exists() and made["collected"] == {"ads": 2, "frames": False}
    assert made["size"]["tokens"] > 0 and made["size"]["band"] in ("low", "medium", "high")


def test_analysis_brief_carries_the_data_and_the_limits(app):
    client, _ = app
    job = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="analysis", deep=2, frames=True)
    made = client.post("/api/brief", json={"job_id": job["id"], "level": "analysis", "ads": 2,
                                           "frames": True, "lang": "it"}).json()
    text = made["text"]
    assert "specialista di performance marketing" in text
    assert "| 835,585 (1 of 1 ads read) |" in text and "| 7,398,228 | 1,679,270 |" in text
    assert "solo per gli annunci mostrati nell'Unione europea o nel Regno Unito" in text
    assert len(made["images"]) == 6 and all(Path(p).exists() for p in made["images"])
    assert Path(made["folder"]).is_dir() and made["collected"] == {"ads": 2, "frames": True}
    fewer = client.post("/api/brief", json={"job_id": job["id"], "level": "analysis", "ads": 1,
                                            "frames": False, "lang": "it"}).json()
    assert fewer["ads"] == 1 and fewer["images"] == [] and fewer["size"]["tokens"] < made["size"]["tokens"]
    assert client.post("/api/brief", json={"job_id": "missing"}).status_code == 404


def test_stills_folder_opens_only_for_packs_the_app_wrote(app):
    client, _ = app
    opened = []
    client.app.state.workspace.opener = opened.append
    job = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="analysis", deep=2, frames=True)
    made = client.post("/api/brief", json={"job_id": job["id"], "level": "analysis", "ads": 2,
                                           "frames": True, "lang": "it"}).json()
    assert made["collected"]["ads"] == job["result"]["deep"]["concepts"]      # concepts read, not ads
    assert made["folder_name"] == Path(made["folder"]).name and made["frames_key"]
    answer = client.post("/api/frames/open", json={"key": made["frames_key"]})
    assert answer.status_code == 200 and answer.json()["pictures"] == 6
    assert opened == [Path(made["folder"]) / "frames"]
    for body in ({"key": "nope"}, {"key": made["folder"]}, {"path": made["folder"]}, {}):
        assert client.post("/api/frames/open", json=body).status_code == 404
    assert len(opened) == 1
    without = client.post("/api/brief", json={"job_id": job["id"], "level": "analysis", "ads": 2,
                                              "frames": False, "lang": "it"}).json()
    assert without["frames_key"] is None                                  # no stills, nothing to open


def test_brief_without_project_is_refused():
    with pytest.raises(ValueError):
        briefs.compose("plan", {"ads": [], "signals": {}}, project=None)
    with pytest.raises(ValueError):
        briefs.compose("data", {"ads": []})


def test_mutating_endpoints_reject_cross_origin_and_malformed_json_and_zero_precheck(tmp_path):
    studio = Studio(tmp_path)
    with TestClient(create_app(studio.client, home=tmp_path / "home"), base_url="http://127.0.0.1:8765") as client:
        for method, path in (
            ("PUT", "/api/project"),
            ("POST", "/api/precheck"),
            ("POST", "/api/jobs"),
            ("POST", "/api/durata"),
            ("POST", "/api/brief"),
            ("POST", "/api/frames/open"),
            ("POST", "/api/video/inspect"),
            ("POST", "/api/ai/run"),
        ):
            bad_orig = client.request(method, path, json={"x": 1}, headers={"Origin": "https://evil.example"})
            assert bad_orig.status_code == 403, (method, path)
            cross = client.request(method, path, json={"x": 1}, headers={"Sec-Fetch-Site": "cross-site"})
            assert cross.status_code == 403, (method, path)

        for method, path in (("PUT", "/api/project"), ("POST", "/api/jobs"), ("POST", "/api/brief"), ("POST", "/api/video/inspect")):
            assert client.request(method, path, content=b"{bad", headers={"Content-Type": "application/json"}).status_code == 400
            assert client.request(method, path, json=["not-a-dict"]).status_code == 400

        assert client.post("/api/precheck", json={"price": 60, "ideas": 0}).status_code == 400
        assert client.post("/api/precheck", json={"price": 60, "multiplier": 0}).status_code == 400
        assert client.post("/api/precheck", json={"price": 60, "ideas": False}).status_code == 400


def test_durata_job_attaches_to_company_job_and_feeds_brief_testing_slice(app):
    client, _ = app
    comp = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="analysis", deep=2)
    assert "durata" not in comp["result"]

    res = client.post("/api/durata", json={"page_id": PAGE_ID, "country": "IT", "window_days": 90})
    assert res.status_code == 202
    djob = res.json()
    for _ in range(200):
        djob = client.get(f"/api/jobs/{djob['id']}").json()
        if djob["status"] != "running":
            break
        time.sleep(0.02)
    assert djob["status"] == "done" and djob["result"]["ritmo"]["snapshots"] == 1
    comp_after = client.get(f"/api/jobs/{comp['id']}").json()
    assert comp_after["result"]["durata"] == djob["result"]["durata"]
    assert comp_after["result"]["ritmo"]["snapshots"] == 1

    made = client.post("/api/brief", json={"job_id": comp["id"], "level": "analysis", "ads": 2, "lang": "en"}).json()
    testing_md = Path(made["files"]["testing"]).read_text(encoding="utf-8")
    assert "## Duration and survival (cohort)" in testing_md
    assert "## Pace and format drift (Ritmo)" in testing_md


def test_trusted_host_middleware_blocks_dns_rebinding_hosts(app):
    client, _ = app
    assert client.get("/api/project", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/project", headers={"Host": "evil.example:8765"}).status_code == 400
    assert client.get("/api/project", headers={"Host": "127.0.0.1:8765"}).status_code == 200
    assert client.get("/api/project", headers={"Host": "localhost:8765"}).status_code == 200
    assert client.get("/api/project").status_code == 200


def test_ai_run_video_inspect_and_history_latest(tmp_path, monkeypatch):
    studio = Studio(tmp_path)
    with TestClient(create_app(studio.client, home=tmp_path / "home"), base_url="http://127.0.0.1:8765") as client:
        job = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="analysis", deep=2)
        latest = client.get("/api/history/latest")
        assert latest.status_code == 200 and latest.json()["available"] is True
        assert latest.json()["result"]["page"]["page_id"] == PAGE_ID

        assert client.post("/api/ai/run", json={"token": "a" * 32, "job_id": job["id"]}).status_code == 403
        same_origin = {"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"}
        assert client.post("/api/ai/run", json={"token": "a" * 32, "job_id": job["id"]}, headers=same_origin).status_code == 403

        tok_a = "a" * 32
        plan_res = client.post(
            "/api/ai/run",
            json={"token": tok_a, "job_id": job["id"], "level": "plan", "ads": 2, "lang": "en"},
            headers={**same_origin, "X-Run-Token": tok_a},
        )
        assert plan_res.status_code == 409 and plan_res.json()["error"] == "project_required"

        monkeypatch.setattr(ai_runner, "run_claude_brief", lambda brief_text, pack_folder, lang="it": {
            "ok": True,
            "markdown": "## Diagnosis\nConcept 1001 leads.",
            "audit": {"status": "ok", "checked_ad_ids": ["1001"], "warning_count": 0, "warnings": []},
        })
        tok_b = "b" * 32
        started = client.post(
            "/api/ai/run",
            json={"token": tok_b, "job_id": job["id"], "level": "analysis", "ads": 2, "lang": "en"},
            headers={**same_origin, "X-Run-Token": tok_b},
        )
        assert started.status_code == 202
        ai_id = started.json()["id"]
        ai_data = None
        for _ in range(100):
            ai_data = client.get(f"/api/ai/jobs/{ai_id}").json()
            if ai_data["status"] != "running":
                break
            time.sleep(0.02)
        assert ai_data and ai_data["status"] == "done"
        assert "Diagnosis" in ai_data["markdown"] and ai_data["audit"]["status"] == "ok"

        replay = client.post(
            "/api/ai/run",
            json={"token": tok_b, "job_id": job["id"], "level": "analysis", "ads": 2},
            headers={**same_origin, "X-Run-Token": tok_b},
        )
        assert replay.status_code == 403 and replay.json()["error"] == "bad_token"

        assert client.post("/api/video/inspect", json={"ad_id": "../bad"}).status_code == 400
        hook_p = tmp_path / "hook.jpg"
        body_p = tmp_path / "body.jpg"
        hook_p.write_bytes(b"\xff\xd8\xff\xe0HOOK")
        body_p.write_bytes(b"\xff\xd8\xff\xe0BODY")

        async def fake_inspect(ad_id, transcribe=False, use_cache=True, media_dir=None):
            return {
                "ok": True, "outcome": "inspected", "ad_id": ad_id,
                "duration": 18.4, "width": 1080, "height": 1920, "aspect_ratio": "9:16",
                "contact_sheets": [
                    {"kind": "hook", "path": str(hook_p)},
                    {"kind": "body", "path": str(body_p)},
                ],
            }

        monkeypatch.setattr(video, "inspect_video", fake_inspect)
        vid = client.post("/api/video/inspect", json={"ad_id": "123456789012"}).json()
        assert vid["ok"] is True and vid["hook_sheet"] == "/media/vid_123456789012_hook.jpg"
        assert client.get(vid["hook_sheet"]).status_code == 200


# --- texts ----------------------------------------------------------------------------

def test_every_text_exists_in_both_languages():
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    assert set(strings) == {"it", "en"}
    assert set(strings["it"]) == set(strings["en"])
    assert all(value.strip() for language in strings.values() for value in language.values())


def test_guide_explains_the_rating_in_both_languages():
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    for language in ("it", "en"):
        words = strings[language]
        assert all(f"guide.q{n}" in words and f"guide.a{n}" in words for n in range(1, 9))
        assert "60" in words["guide.a3"] and "25" in words["guide.a3"] and "15" in words["guide.a3"]
        assert "50, 30" not in words["guide.a4"]                  # the points no longer change with what is known
        assert "60" in words["guide.example"] and "44" in words["guide.example"]
        for verdict in ("scaling", "holding", "testing", "review", "average", "ended"):
            assert words[f"verdict.{verdict}"] in words["guide.a5"]
        assert "7" in words["guide.a3"] and "7" in words["guide.a5"]         # never over fewer than seven days


def test_page_uses_only_texts_that_exist():
    import re
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))["it"]
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    literal = set(re.findall(r"""\bt\('([a-z0-9_.]+)'""", script))
    assert literal and not sorted(key for key in literal if key not in strings)
    counted = set(re.findall(r"""\bcount\([^;]*?, '([a-z0-9_.]+)'\)""", script))   # one and other
    assert counted and not sorted(f"{key}.{form}" for key in counted for form in ("one", "other")
                                  if f"{key}.{form}" not in strings)


# --- the page in a browser, on saved data ---------------------------------------------
# A real server on 127.0.0.1 with the scripted client: no request leaves the computer.

def _post(base, path, body):
    import urllib.request
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request) as answer:
        return json.loads(answer.read())


def _get(base, path):
    import urllib.request
    with urllib.request.urlopen(base + path) as answer:
        return json.loads(answer.read())


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    import socket
    import threading
    from types import SimpleNamespace

    sync_api = pytest.importorskip("playwright.sync_api")
    import uvicorn

    tmp = tmp_path_factory.mktemp("site")
    web = create_app(Studio(tmp).client, home=tmp / "home")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(250):
        if server.started:
            break
        time.sleep(0.02)
    base = f"http://127.0.0.1:{port}"
    job = _post(base, "/api/jobs", {"mode": "company", "page_id": PAGE_ID, "country": "IT",
                                    "level": "analysis", "deep": 2, "frames": True})
    for _ in range(250):
        job = _get(base, f"/api/jobs/{job['id']}")
        if job["status"] != "running":
            break
        time.sleep(0.02)
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:                      # no browser installed on this machine
            pytest.skip(f"no browser for the page tests: {exc}")
        yield SimpleNamespace(base=base, browser=browser, web=web, job=job, home=tmp / "home")
        browser.close()
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def page_of(site):
    contexts, errors = [], []

    def open_page(lang="it", result=None, link=None, hold=False):
        context = site.browser.new_context(viewport={"width": 1440, "height": 900})
        contexts.append(context)
        page = context.new_page()
        _serve_link(page, *(link or (NO_CLAUDE, "no_claude")), hold=hold)      # never ask the real Claude Code
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(f"try {{ localStorage.setItem('lang', '{lang}'); }} catch (e) {{}}")
        page.goto(site.base)
        page.wait_for_function("typeof T !== 'undefined' && Object.keys(T.it).length > 0")
        if result is not None:
            page.evaluate("""([r, id]) => { S.mode = r.mode; S.result = r; S.resultMode = r.mode;
                S.jobId = id; S.pages = null; S.overlay = null; render(); }""", [result, site.job["id"]])
        return page

    yield open_page
    for context in contexts:
        context.close()
    assert not errors


def _result(site, **changes):
    result = json.loads(json.dumps(site.job["result"]))
    for key, value in changes.items():
        result[key] = value
    return result


def test_page_brief_text_is_never_shown_and_copies_with_a_confirmation(site, page_of):
    page = page_of("it", _result(site))
    page.click("[data-action=brief]")
    page.wait_for_selector(".dialog [data-action=copy-brief]")
    made = page.evaluate("S.overlay.made")
    html = page.content()
    assert page.locator("textarea").count() == 0
    assert "specialista di performance marketing" in made["text"]
    assert "specialista di performance marketing" not in html and made["text"][:200] not in html
    assert made["folder"] not in html and str(site.home) not in html     # no path of the computer
    assert made["folder_name"] in html
    page.evaluate("navigator.clipboard.writeText = async (text) => { window.copied = text; }")
    page.click("[data-action=copy-brief]")
    page.wait_for_function("document.querySelector('.status').textContent.length > 0")
    assert page.evaluate("window.copied") == made["text"]
    assert page.inner_text(".status") == "Testo copiato. Incollalo nel tuo assistente."
    assert page.inner_text("[data-action=copy-brief]") == "Copia per il tuo assistente"
    page.click("[data-action=copy-command]")
    page.wait_for_function("document.querySelector('.status').textContent.startsWith('Comando')")
    assert made["folder"] in page.evaluate("window.copied")              # copied whole, shown by name


def test_page_copy_falls_back_without_the_clipboard_api(site, page_of):
    page = page_of("en", _result(site))
    page.evaluate("""() => { Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
        document.execCommand = (name) => { window.fallback = [name, document.querySelector('textarea.offscreen').value]; return true; }; }""")
    page.click("[data-action=brief]")
    page.wait_for_selector(".dialog [data-action=copy-brief]")
    assert page.inner_text("[data-action=copy-brief]") == "Copy for your assistant"
    page.click("[data-action=copy-brief]")
    page.wait_for_function("document.querySelector('.status').textContent.length > 0")
    name, copied = page.evaluate("window.fallback")
    assert name == "copy" and copied == page.evaluate("S.overlay.made.text")
    assert page.inner_text(".status") == "Text copied. Paste it into your assistant."
    assert page.locator("textarea").count() == 0                         # the helper box is gone again
    page.evaluate("document.execCommand = () => false")
    page.click("[data-action=copy-brief]")
    page.wait_for_function("document.querySelector('.status.err') !== null")
    assert "brief.md" in page.inner_text(".status")


def test_page_opens_the_stills_folder_only_when_there_are_stills(site, page_of):
    opened = []
    site.web.state.workspace.opener = opened.append
    page = page_of("it", _result(site))
    page.click("[data-action=brief]")
    page.wait_for_selector("[data-action=open-frames]")
    assert page.inner_text("[data-action=open-frames]") == "Apri cartella fotogrammi"
    page.click("[data-action=open-frames]")
    page.wait_for_function("document.querySelector('.status').textContent.length > 0")
    assert page.inner_text(".status") == "Cartella dei fotogrammi aperta sul tuo computer."
    assert len(opened) == 1 and opened[0].name == "frames" and opened[0].is_dir()
    assert str(opened[0]) not in page.content()
    page.uncheck("[data-change=brief-frames]")
    page.wait_for_function("document.querySelector('[data-action=open-frames]') === null")


def test_page_shows_the_usage_estimate_before_starting(site, page_of):
    for lang, words in (("it", ["Concetti da leggere", "al massimo 20, due per concetto", "30 immagini",
                                "token", "Consumo stimato", "Sono stime"]),
                        ("en", ["Concepts to read", "at most 20, two per concept", "30 pictures",
                                "tokens", "Estimated usage", "These are estimates"])):
        page = page_of(lang)
        page.evaluate("() => { S.level = 'analysis'; S.frames = true; S.query = 'desk'; render(); gate({ mode: 'keyword', query: 'desk' }); }")
        page.wait_for_function("S.estimate && S.estimate.level === 'analysis' && S.estimate.images === 30 && document.querySelector('.dialog [data-action=confirm-go]')")
        page.wait_for_timeout(50)
        text = page.inner_text(".dialog")
        assert all(word in text for word in words), (lang, text)
        assert "%" not in text                                           # no promise of a share of a limit
        band = page.inner_text(".dialog .v.big")
        assert band in ("Basso", "Medio", "Alto", "Low", "Medium", "High")


def test_page_says_concepts_and_explains_the_ceiling(site, page_of):
    deep = {"requested": 20, "read": 40, "concepts": 18, "failed": [], "with_reach": 18, "ceiling": 40,
            "capped": True, "left_out": 7, "ceiling_note": "Stopped at the ceiling of 40 ads opened", "note": None}
    page = page_of("it", _result(site, deep=deep))
    text = page.inner_text("#results")
    assert ("Letti 18 concetti su 20: raggiunto il tetto di 40 annunci aperti. Di questi concetti "
            "restano chiusi 7 annunci: la loro copertura è un minimo.") in text
    assert "Stopped at the ceiling" not in page.content()
    page.click("[data-action=search-expand]")
    assert "concetti della classifica" in page.inner_text("#search")
    page.click("[data-action=rtab][data-value=ads]")
    ads_text = page.inner_text("#results")
    assert "Copertura letta per 18 concetti" in ads_text and "aprendo 40 annunci" in ads_text
    page = page_of("en", _result(site, deep={**deep, "left_out": 1}))
    text = page.inner_text("#results")
    assert ("Read 18 concepts out of 20: the ceiling of 40 ads opened was reached. 1 more ad of these "
            "concepts was left closed: their reach is a floor.") in text
    page = page_of("it", _result(site, deep={**deep, "capped": False}))
    assert "tetto" not in page.inner_text("#results")


PLACES = ["France", "Germany", "Spain", "Austria", "Belgium", "Poland", "Portugal", "Greece", "Ireland"]


def _with_audience(site, ranges):
    result = _result(site)
    audience = result["signals"]["audience"]
    audience.update(age_ranges=ranges, ads_with_audience=sum(r["ads"] for r in ranges))
    every = audience["ads_with_audience"]
    audience.update(locations_excluded=[{"name": name, "type": "countries", "ads": every} for name in PLACES],
                    locations_excluded_count=len(PLACES))
    return result


def test_page_shows_age_as_a_range_and_sums_up_excluded_places(site, page_of):
    page = page_of("it", _with_audience(site, [{"age_min": 25, "age_max": 65, "ads": 3}]))
    facts = page.inner_text("section.facts")
    assert "25-65+" in facts and "25\n65" not in facts
    assert "9 luoghi: Francia, Germania, Spagna e altri 6" in facts and "Grecia" not in facts
    page = page_of("en", _with_audience(site, [{"age_min": 25, "age_max": 65, "ads": 2},
                                               {"age_min": 20, "age_max": 64, "ads": 1}]))
    facts = page.inner_text("section.facts")
    assert "25-65+ 2 of 3, plus 1 other range" in facts and "20-64" not in facts
    assert "9 locations: France, Germany, Spain and 6 more" in facts


def test_page_shows_the_category_of_the_advertiser_page(site, page_of):
    result = _result(site)
    assert result["page"]["category"]
    page = page_of("it", result)
    assert f"{result['page']['category']} · " in page.inner_text("section.rhead")
    result["page"]["category"] = None
    page = page_of("it", result)
    head = page.inner_text("section.rhead p")
    assert head.split("\n")[0].endswith("seguaci · Italia") and "—" not in head.split("\n")[0]


def test_page_says_one_day_in_the_singular(site, page_of):
    result = _result(site)
    ad = result["ads"][0]
    ad.update(days_running=1, ad_days=1, too_recent=True)
    for lang, one, wrong in (("it", "1 giorno", "1 giorni"), ("en", "1 day", "1 days")):
        page = page_of(lang, result)
        page.evaluate("(id) => { S.overlay = { type: 'ad', id }; renderOverlay(); }", ad["library_id"])
        drawer = page.inner_text(".drawer")
        assert one in drawer and not re.search(rf"(?<!\d){re.escape(wrong)}", drawer)
        page.evaluate("(id) => { const ad = findAd(id); ad.days_running = 12; ad.too_recent = false; renderOverlay(); }",
                      ad["library_id"])
        assert ("12 giorni" if lang == "it" else "12 days") in page.inner_text(".drawer")


def test_estimate_uses_the_measured_tokens_per_concept():
    assert consumption.TOKENS_PER_AD == 400
    assert consumption.estimate("analysis", 10)["tokens"] == 22500      # (2500 + 10 * 400) * 3 + 3000


def test_stills_folder_refuses_bad_bodies_and_foreign_origins(app):
    client, _ = app
    opened = []
    client.app.state.workspace.opener = opened.append
    job = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="analysis", deep=2, frames=True)
    made = client.post("/api/brief", json={"job_id": job["id"], "level": "analysis", "ads": 2,
                                           "frames": True, "lang": "it"}).json()
    assert client.post("/api/frames/open", content=b"not json").status_code == 400
    assert client.post("/api/frames/open", json=["key"]).status_code == 400
    assert client.post("/api/frames/open", json={"key": made["frames_key"]},
                       headers={"Origin": "https://evil.example"}).status_code == 403
    assert opened == []
    ok = client.post("/api/frames/open", json={"key": made["frames_key"]},
                     headers={"Origin": "http://127.0.0.1"})
    assert ok.status_code == 200 and len(opened) == 1


def test_collected_count_is_zero_when_no_concept_was_read(app):
    client, _ = app
    job = run_job(client, mode="company", page_id=PAGE_ID, country="IT", level="analysis", deep=2)
    client.app.state.workspace.jobs[job["id"]].raw["deep"] = {"concepts": 0}
    made = client.post("/api/brief", json={"job_id": job["id"], "level": "analysis", "ads": 2,
                                           "frames": False, "lang": "it"}).json()
    assert made["collected"]["ads"] == 0


def test_page_failed_command_copy_talks_about_the_command(site, page_of):
    for lang, hand in (("it", "La copia non"), ("en", "The copy did not work")):
        page = page_of(lang, _result(site))
        page.evaluate("""() => { Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
            document.execCommand = () => false; }""")
        page.click("[data-action=brief]")
        page.wait_for_selector(".dialog [data-action=copy-command]")
        page.click("[data-action=copy-command]")
        page.wait_for_function("document.querySelector('.status.err') !== null")
        shown = page.inner_text(".status")
        assert hand in shown and "brief.md" in shown and "\\" not in shown and ":/" not in shown


def test_table_note_agrees_with_one_concept_and_texts_say_concepts():
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    for language in ("it", "en"):
        assert "t.note" in strings[language] and "t.note.one" in strings[language]
    assert "concetto" in strings["it"]["lv.data.3"] and "concept" in strings["en"]["lv.data.3"]
    assert "concetti" in strings["it"]["d.reach.unread"] and "concepts" in strings["en"]["d.reach.unread"]
    assert "ads" not in strings["en"]["d.reach.unread"] and "annunci" not in strings["it"]["d.reach.unread"]


def test_page_table_note_is_singular_for_one_concept(site, page_of):
    result = _result(site)
    result["deep"]["concepts"] = 1
    result["deep"]["read"] = 1
    for lang, expected, wrong in (("it", "per 1 concetto, il più mostrato", "i più mostrati"),
                                  ("en", "for 1 concept, the one most shown", "the most shown")):
        page = page_of(lang, result)
        page.click("[data-action=rtab][data-value=ads]")
        note = page.inner_text("p.tablenote")
        assert expected in note and wrong not in note


def test_page_age_range_reads_cleanly(site, page_of):
    page = page_of("it", _result(site))
    got = page.evaluate("[[65, null], [65, 65], [30, 30], [null, 30], [25, 44], [18, null], [45, 70], [null, null]].map(([a, b]) => ageRange(a, b))")
    assert got == ["65+", "65+", "30", "18-30", "25-44", "18-65+", "45-65+", "—"]


def test_page_table_shows_reach_when_only_a_later_ad_of_the_concept_was_read(site, page_of):
    result = _result(site)
    ad = result["ads"][0]
    ad.update(reach=None, reach_total=123456, reach_per_day=789, cards=3, reach_cards_read=2)
    page = page_of("en", result)
    page.click("[data-action=rtab][data-value=ads]")
    row = page.locator("table.ads tbody tr").filter(has_text=f"{123456:,}").first
    cells = row.locator("td.r")
    texts = cells.all_inner_texts()
    assert "123,456" in texts and "789" in texts
    assert "2 ads read out of 3" in (cells.filter(has_text="123,456").first.get_attribute("title") or "")


def test_page_refused_project_card_shows_errors_without_a_failed_request(site, page_of):
    page = page_of("it")
    failed = []
    page.on("response", lambda response: failed.append(response.url) if response.status >= 400 else None)
    page.click("[data-action=project]")
    page.click("[data-action=save-project]")
    page.wait_for_selector(".field.bad em")
    assert page.locator(".field.bad").count() >= 3
    assert failed == []


def test_project_goal_hint_fits_the_half_width_field():
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    for language in ("it", "en"):
        assert len(strings[language]["proj.goal.hint"]) <= 26      # the field is half the dialog: a longer hint is cut


def test_page_one_creative_reads_in_the_singular(site, page_of):
    for lang, expected, wrong in (("it", "1 creativit\u00e0 per questo concetto", "1 creativit\u00e0 diverse"),
                                  ("en", "1 creative for this concept", "1 creatives")):
        result = _result(site)
        result["ads"][0]["creatives"] = 1
        page = page_of(lang, result)
        page.evaluate("(id) => { S.overlay = { type: 'ad', id }; renderOverlay(); }", result["ads"][0]["library_id"])
        page.wait_for_selector(".drawer")
        shown = page.inner_text(".drawer")
        assert expected in shown and wrong not in shown
        assert page.evaluate("t('f.reused.n.one')") in ("1 creativit\u00e0", "1 creative")


def test_page_one_hour_between_searches_reads_in_the_singular(page_of):
    for lang, one, many in (("it", "1 ora", "3 ore"), ("en", "1 hour", "3 hours")):
        page = page_of(lang)
        assert page.evaluate("oneOrMore('gap.hours', 1)") == one
        assert page.evaluate("oneOrMore('gap.hours', 3)") == many


def test_page_shows_the_initials_when_the_logo_of_a_page_does_not_load(site, page_of):
    result = _result(site)
    result["page"]["name"] = "Northwind Desks"
    result["page"]["logo"] = "/media/no-such-logo.jpg"                   # the picture is not there: the request fails
    page = page_of("it", result)
    page.wait_for_selector("section.rhead span.avatar.txt")
    assert page.inner_text("section.rhead span.avatar.txt") == "ND"
    assert page.locator("section.rhead img.avatar").count() == 0


# --- levels and connection screen ----------------------------------------------------------

READY = {"claude": True, "skills": {"available": True, "total": 4, "missing": 4, "modified": [], "installed": False},
         "command": "claude mcp add ad-library-insights --scope user -- python -m ad_library_insights",
         "skills_folder": "~/.claude/skills"}
DONE = {**READY, "skills": {**READY["skills"], "missing": 0, "installed": True}}
NO_CLAUDE = {**READY, "claude": False}


def _serve_link(page, status, mcp, hold=False):
    """Answer the three connection requests with canned data. ``page.posted`` collects what the page
    sent to connect; with ``hold`` the slow check stays pending in ``page.held`` until the test answers."""
    page.posted, page.held = [], []

    def on_mcp(route):
        if hold:
            page.held.append(route)
        else:
            route.fulfill(json={"state": mcp})

    def on_connect(route):
        page.posted.append({"headers": route.request.headers, "body": json.loads(route.request.post_data)})
        route.fulfill(json={"ok": True, "server": "added", "skills": {"copied": 4, "kept": []}})

    page.route("**/api/link/status", lambda route: route.fulfill(json=status))
    page.route("**/api/link/mcp", on_mcp)
    page.route("**/api/link/connect", on_connect)


def _open_rows(page):
    return page.evaluate("[...document.querySelectorAll('.lvl')].map((r) => r.classList.contains('open'))")


def _count(page, selector):
    return page.locator(selector).count()


def test_page_opening_a_level_row_chooses_it_and_the_state_is_remembered(site, page_of):
    page = page_of("it")
    page.wait_for_selector(".lvl")
    assert _open_rows(page) == [True, False, False] and page.evaluate("S.level") == "data"
    assert "Profondità dell'indagine e livello di elaborazione" in page.inner_text(".levels-head")
    assert _count(page, "#lv-plan li") == 4 and _count(page, "#lv-data li") == 4
    assert page.is_visible("#lv-data") and page.is_hidden("#lv-plan")
    assert _count(page, ".lvl-body .btn") == 0                         # no button to choose: opening chooses
    page.click(".lvl-head[data-value=plan]")                           # opens level 3 and closes level 1
    assert _open_rows(page) == [False, False, True] and page.evaluate("S.level") == "plan"
    assert page.evaluate("[...document.querySelectorAll('.lvl')].map((r) => r.classList.contains('chosen'))") == [False, False, True]
    page.reload()
    page.wait_for_selector(".lvl")
    assert _open_rows(page) == [False, False, True] and page.evaluate("S.level") == "plan"
    page.click(".lvl-head[data-value=plan]")                           # the open row closes; the level stays chosen
    assert _open_rows(page) == [False, False, False] and page.evaluate("S.level") == "plan"
    page.reload()
    page.wait_for_selector(".lvl")
    assert _open_rows(page) == [False, False, False] and page.evaluate("S.level") == "plan"


def test_page_one_main_button_in_the_way_section_and_no_level_called_by_its_old_name(site, page_of):
    for lang, plan_text in (("it", "serve per il livello 3"), ("en", "needed for level 3")):
        page = page_of(lang)
        page.wait_for_selector(".ways")
        mains = page.evaluate("[...document.querySelectorAll('.way .btn')].filter((b) => !b.classList.contains('quiet')).map((b) => b.dataset.action)")
        assert mains == ["link-open"]
        assert page.evaluate("document.querySelector('[data-action=way-copy]').classList.contains('quiet')")
        assert plan_text in page.inner_text(".options")
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    names = {"it": ("Dati", "Analisi", "Piano"), "en": ("Data", "Analysis", "Plan")}
    for language, words in names.items():
        for key, value in strings[language].items():
            if key.startswith(("guide.", "brief.", "d.")):
                continue
            assert not any(re.search(rf"\b{word}\b", value) for word in words), (language, key, value)


def test_page_connection_shows_three_states_and_runs_only_after_the_confirmation(site, page_of):
    page = page_of("it", link=(READY, "missing"))
    page.wait_for_function("document.querySelectorAll('.checks li.todo').length === 2")
    assert _count(page, ".checks li.ok") == 1 and "da fare" in page.inner_text(".checks")
    page.click("[data-action=link-open]")
    page.wait_for_selector(".dialog .command")
    assert page.inner_text(".dialog .command") == READY["command"] and page.posted == []
    page.click(".dialog [data-action=close]")
    assert page.posted == []
    page.click("[data-action=link-open]")
    _serve_link(page, DONE, "connected")
    page.click("[data-action=link-go]")
    page.wait_for_function("document.querySelectorAll('.checks li.ok').length === 3")
    assert len(page.posted) == 1
    token = page.posted[0]["body"]["token"]
    assert page.posted[0]["headers"]["x-link-token"] == token and len(token) == 32
    assert "Fatto" in page.inner_text(".way-card") and "Copiati 4" in page.inner_text(".way-card")
    assert page.inner_text("[data-action=link-open]") == "Già collegato" and page.is_disabled("[data-action=link-open]")
    assert "riaprila" in page.inner_text(".way-after")
    page.click("[data-action=link-test]")
    page.wait_for_function("document.querySelector('.way-card').innerText.includes('vede il programma')")


def test_page_connection_says_when_the_slow_check_is_running(site, page_of):
    page = page_of("it", link=(READY, "connected"), hold=True)
    page.wait_for_function("document.querySelectorAll('.checks li.checking').length === 1")
    assert "controllo in corso" in page.inner_text(".checks")
    assert _count(page, ".checks li.ok") == 1                       # Claude Code found: shown without waiting
    page.held[0].fulfill(json={"state": "connected"})
    page.wait_for_function("document.querySelectorAll('.checks li.checking').length === 0")
    assert _count(page, ".checks li.ok") == 2 and _count(page, ".checks li.todo") == 1


def test_page_connection_without_claude_code_explains_and_links_to_the_install_page(site, page_of):
    page = page_of("it", link=(NO_CLAUDE, "no_claude"))
    page.wait_for_function("document.querySelector('.way-card a')")
    assert "non è stato trovato" in page.inner_text(".way-card")
    assert page.get_attribute(".way-card a", "href").startswith("https://") and page.is_disabled("[data-action=link-open]")
    assert _count(page, ".checks li.ok") == 0 and _count(page, "[data-action=link-test]") == 0


def test_page_connection_reports_a_failed_command_and_a_kept_skill_file(site, page_of):
    page = page_of("it", link=(READY, "missing"))
    page.wait_for_function("document.querySelectorAll('.checks li.todo').length === 2")
    page.route("**/api/link/connect", lambda route: route.fulfill(
        status=500, json={"ok": False, "error": "command_failed", "detail": "boom: could not write"}))
    page.click("[data-action=link-open]")
    page.click("[data-action=link-go]")
    page.wait_for_selector(".way-detail")
    assert "boom: could not write" in page.inner_text(".way-detail") and "non è riuscito" in page.inner_text(".way-card")
    page.unroute("**/api/link/connect")
    page.route("**/api/link/connect", lambda route: route.fulfill(json={
        "ok": True, "server": "already", "skills": {"copied": 0, "kept": ["alpha/SKILL.md"]}}))
    page.click("[data-action=link-open]")
    page.click("[data-action=link-go]")
    page.wait_for_selector("[data-action=link-overwrite-open]")
    assert "Era già collegato" in page.inner_text(".way-card")
    page.click("[data-action=link-overwrite-open]")
    page.wait_for_selector(".dialog .files")
    assert "alpha/SKILL.md" in page.inner_text(".dialog .files")


def test_page_copy_the_text_card_needs_a_search_with_level_two_or_three(site, page_of):
    page = page_of("it")
    page.click("[data-action=way-copy]")
    assert "Prima fai una ricerca" in page.inner_text(".ways")
    page = page_of("it", _result(site))
    page.click("[data-action=search-expand]")
    page.click("[data-action=way-copy]")
    page.wait_for_selector(".dialog [data-action=copy-brief]")


def test_page_how_it_works_has_three_screens_and_the_plan_button_is_marked_soon(site, page_of):
    page = page_of("en")
    page.wait_for_selector("[data-action=way-run]")
    assert page.is_disabled("[data-action=way-run]")
    page_ready = page_of("en", link=(READY, "connected"))
    page_ready.wait_for_selector("[data-action=way-run]:not([disabled])")
    page_ready.click("[data-action=way-run]")
    assert "First search a company or keyword" in page_ready.inner_text(".ways")
    page.click("[data-action=how-open]")
    assert "Step 1 of 3" in page.inner_text(".dialog") and page.is_disabled("[data-action=how-prev]")
    page.click("[data-action=how-next]")
    page.click("[data-action=how-next]")
    assert "Step 3 of 3" in page.inner_text(".dialog") and "Ask for the plan" in page.inner_text(".dialog")
    page.click(".dialog [data-action=close]")
    assert _count(page, ".dialog") == 0


SAMPLE_DURATA = {
    "available": True,
    "unit": "concept",
    "mode": "company",
    "active_status": "all",
    "loaded_share": 1.0,
    "window_days": 90,
    "as_of": "2026-11-13",
    "concepts_in_window": 14,
    "active_in_window": 6,
    "ended_in_window": 8,
    "excluded_undated": 0,
    "excluded_invalid": 0,
    "outside_window": 0,
    "max_observed_days": 90,
    "tau_days": 90,
    "median_days": 22.0,
    "median_reached": True,
    "rmst_days": 34.5,
    "milestones": {"7": 0.79, "14": 0.64, "30": 0.43, "60": 0.29, "90": 0.21},
    "curve": [
        {"day": 5, "at_risk": 14, "ended": 3, "survival": 0.7857, "se": 0.1097, "ci_low": 0.4725, "ci_high": 0.9254},
        {"day": 14, "at_risk": 11, "ended": 2, "survival": 0.6429, "se": 0.1281, "ci_low": 0.3433, "ci_high": 0.8332},
        {"day": 22, "at_risk": 9, "ended": 2, "survival": 0.5, "se": 0.1336, "ci_low": 0.2287, "ci_high": 0.7224},
        {"day": 45, "at_risk": 6, "ended": 1, "survival": 0.4167, "se": 0.1337, "ci_low": 0.165, "ci_high": 0.6542},
    ],
    "weibull": {"shape_k": 0.78, "scale_days": 28.4, "regime": "early_cut"},
    "lindy": [{"after_days": 30, "horizon_days": 30, "at_risk": 6, "still_active_share": 0.67}],
    "longest_active": [{"library_id": "101", "days": 85, "started": "2026-08-20"}],
    "fastest_ended": [{"library_id": "202", "days": 3, "started": "2026-11-01", "ended": "2026-11-04"}],
}


def test_page_theme_transition_and_sticky_language_switch(site, page_of):
    page = page_of("it", _result(site))
    assert _count(page, ".topbar #lang [data-action=lang]") == 2
    assert _count(page, ".topbar #theme [data-action=theme]") == 2
    page.click(".topbar [data-action=theme][data-value=dark]")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.evaluate("document.documentElement.classList.contains('theme-transition')") is True
    page.wait_for_function("!document.documentElement.classList.contains('theme-transition')", timeout=2000)

    assert "in breve" in page.inner_text(".tldr").casefold()
    page.click(".topbar [data-action=lang][data-value=en]")
    assert page.evaluate("document.documentElement.lang") == "en"
    assert "at a glance" in page.inner_text(".tldr").casefold()
    page.click(".topbar [data-action=mode][data-value=news]")
    assert _count(page, ".topbar #lang [data-action=lang]") == 2
    assert "What changed" in page.inner_text("#search h1")


def test_page_shows_tldr_and_help_popovers_within_viewport(site, page_of):
    comp = _result(site, durata=SAMPLE_DURATA)
    page = page_of("it", comp)
    tldr = page.inner_text(".tldr")
    assert "in breve" in tldr.casefold() and "22 giorni" in tldr

    # Check ? help popovers on table headers inside the Ads tab fit inside 1440px viewport and close on Escape
    page.click("[data-action=rtab][data-value=ads]")
    for idx in range(3):
        btn = page.locator("table.ads thead [data-action=help-toggle]").nth(idx)
        btn.click()
        pop = page.locator(".help-wrap.open .help-pop")
        assert pop.is_visible()
        box = pop.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 1440
        page.keyboard.press("Escape")
        assert _count(page, ".help-wrap.open") == 0

    # Open ad drawer, toggle its ? popover, press Escape -> closes popover FIRST without closing drawer
    page.locator("table.ads tbody tr").first.click()
    page.wait_for_selector(".drawer")
    page.locator(".drawer [data-action=help-toggle]").first.click()
    assert _count(page, ".drawer .help-wrap.open") == 1
    page.keyboard.press("Escape")
    assert _count(page, ".drawer .help-wrap.open") == 0 and _count(page, ".drawer") == 1

    # Also verify automatic In breve renders cleanly in keyword mode
    kw = _result(site, mode="keyword", query="standing desk", page=None)
    page = page_of("en", kw)
    assert "keyword sample" in page.inner_text(".tldr")


def test_page_durata_section_renders_states_svg_and_runs_endpoint(site, page_of):
    # Keyword mode -> locked bar (inside Durata & survival tab)
    kw = _result(site, mode="keyword", query="standing desk", page=None)
    page = page_of("it", kw)
    page.click("[data-action=rtab][data-value=durata]")
    assert "Analizza un'azienda" in page.inner_text(".durata-locked")

    # Partial list -> honest explanation (both low loaded_share and unverified None)
    partial = _result(site, durata={"available": False, "reason": "partial_list", "loaded_share": 0.55, "window_days": 90})
    page = page_of("it", partial)
    page.click("[data-action=rtab][data-value=durata]")
    assert "55%" in page.inner_text(".durata-sec")

    unverified = _result(site, durata={"available": False, "reason": "partial_list", "loaded_share": None, "window_days": 90})
    page = page_of("it", unverified)
    page.click("[data-action=rtab][data-value=durata]")
    assert "non verificata" in page.inner_text(".durata-sec")

    # Populated Durata in Light & Dark, IT & EN
    populated = _result(site, durata=SAMPLE_DURATA)
    for lang, expected_word, expected_small in (("it", "Taglio rapido iniziale", "Campione piccolo"),
                                                ("en", "Early cut", "Small sample")):
        page = page_of(lang, populated)
        if lang == "en":
            page.click(".topbar [data-action=theme][data-value=dark]")
        page.click("[data-action=rtab][data-value=durata]")
        sec = page.inner_text(".durata-sec")
        assert expected_word in sec and expected_small in sec and "101" in sec and "202" in sec
        assert _count(page, ".durata-chart svg path") >= 1
        assert _count(page, ".durata-chart svg polygon") == 1

    # Clicking Run triggers POST /api/durata and updates UI cleanly
    base_res = _result(site)
    page = page_of("it", base_res)
    page.click("[data-action=rtab][data-value=durata]")
    posted = []
    page.route("**/api/durata", lambda route: (
        posted.append(json.loads(route.request.post_data)),
        route.fulfill(status=202, json={"id": "durjob1", "status": "running", "phase": "list"}),
    ))
    page.route("**/api/jobs/durjob1", lambda route: route.fulfill(
        json={"id": "durjob1", "status": "done", "result": {"ok": True, "durata": SAMPLE_DURATA}},
    ))
    page.click("[data-action=durata-window][data-value='120']")
    page.click("[data-action=durata-run]")
    page.wait_for_selector(".durata-chart svg")
    assert posted == [{"page_id": PAGE_ID, "country": "IT", "window_days": 120, "fresh": False}]
    assert "22 giorni" in page.inner_text(".durata-sec")


def test_page_level3_prova_prima_di_spendere_updates_live_and_saves_optional_costs(site, page_of):
    page = page_of("it")
    page.click(".lvl-head[data-value=plan]")
    page.wait_for_selector(".precheck-box")
    assert _count(page, "#lv-plan li") == 4
    assert _count(page, ".lvl-body .btn") == 0

    vis_text = page.inner_text("#lv-plan .lvl-vis")
    assert "1,06" in vis_text and "0,82" in vis_text and "1,28" in vis_text
    assert _count(page, "#lv-plan .jury-card") == 4

    # Live updates when editing price, cost, shipping and toggling Italy +3% fee
    page.fill("[data-sim=price]", "100")
    page.fill("[data-sim=cost]", "30")
    page.click(".sim-extra summary")
    page.fill("[data-sim=ship]", "10")
    cpa_it = page.inner_text("#sim-cpa")
    risk_it = page.inner_text("#sim-risk-line")
    page.uncheck("[data-sim-check=itFee]")
    cpa_no_fee = page.inner_text("#sim-cpa")
    risk_no_fee = page.inner_text("#sim-risk-line")
    assert cpa_no_fee == "60" and cpa_it != cpa_no_fee
    assert risk_it != risk_no_fee

    # English + Dark mode check
    page.click(".topbar [data-action=lang][data-value=en]")
    page.click(".topbar [data-action=theme][data-value=dark]")
    en_text = page.inner_text("#lv-plan .lvl-vis")
    assert "1.06" in en_text and "Skeptical jury" in en_text

    # Save project card with optional real costs and verify persistence
    page.click("[data-action=project]")
    page.wait_for_selector(".proj-extra")
    page.fill("[data-pf=product]", "Test Item")
    page.fill("[data-pf=price]", "100")
    page.fill("[data-pf=product_cost]", "30")
    page.fill("[data-pf=goal]", "10")
    page.fill("[data-pf=main_problem]", "High CPA")
    page.click(".proj-extra summary")
    page.fill("[data-pf=shipping_cost]", "5")
    page.fill("[data-pf=return_rate_pct]", "10")
    page.click("[data-action=save-project]")
    page.wait_for_function("S.project && S.project.shipping_cost === 5")

    page.click("[data-action=project]")
    page.wait_for_selector(".proj-extra[open]")
    assert page.input_value("[data-pf=shipping_cost]") == "5"
    assert page.input_value("[data-pf=return_rate_pct]") == "10"


SAMPLE_RITMO = {
    "available": True,
    "unit": "concept",
    "mode": "company",
    "loaded_share": 1.0,
    "as_of": "2026-11-13",
    "snapshots": 3,
    "source": "snapshots",
    "survivor_bias": False,
    "snapshot_span_days": 28,
    "status": "alert",
    "trigger_ai": True,
    "alerts": ["launch_spike", "format_drift"],
    "sta_lta": {
        "measurable": True,
        "state": "spike",
        "sta_count": 8,
        "lta_total": 16,
        "lta_mean": 2.0,
        "ratio": 4.0,
        "p_value": 0.0021,
        "recent_ids": ["901", "902"],
        "survivor_bias_caveat": True,
        "trigger_ai": True,
        "weeks": [
            {"week_start": "2026-09-12", "week_end": "2026-09-18", "concepts": 2, "is_sta": False},
            {"week_start": "2026-09-19", "week_end": "2026-09-25", "concepts": 1, "is_sta": False},
            {"week_start": "2026-09-26", "week_end": "2026-10-02", "concepts": 3, "is_sta": False},
            {"week_start": "2026-10-03", "week_end": "2026-10-09", "concepts": 2, "is_sta": False},
            {"week_start": "2026-10-10", "week_end": "2026-10-16", "concepts": 2, "is_sta": False},
            {"week_start": "2026-10-17", "week_end": "2026-10-23", "concepts": 2, "is_sta": False},
            {"week_start": "2026-10-24", "week_end": "2026-10-30", "concepts": 2, "is_sta": False},
            {"week_start": "2026-10-31", "week_end": "2026-11-06", "concepts": 2, "is_sta": False},
            {"week_start": "2026-11-07", "week_end": "2026-11-13", "concepts": 8, "is_sta": True},
        ],
    },
    "cusum": {
        "measurable": True,
        "concepts": 24,
        "span_days": 45,
        "split_date": "2026-10-15",
        "drift_detected": True,
        "trigger_ai": True,
        "primary": {
            "format": "video",
            "baseline_share": 0.25,
            "recent_share": 0.75,
            "delta_share": 0.5,
            "cusum_peak": 5.2,
            "threshold": 4.0,
            "direction": "up",
            "changepoint_date": "2026-10-20",
        },
        "example_ids": ["902", "903"],
        "formats": [],
    },
    "littles_law": {
        "measurable": True,
        "active_concepts": 18,
        "launches_28d": 12,
        "window_days": 28,
        "lambda_per_week": 3.0,
        "implied_mean_days": 42.0,
        "steady_state_checked": True,
        "mean_duration_days": 34.5,
        "expected_active": 14.8,
        "balance_ratio": 1.22,
        "balance_state": "balanced",
    },
    "snapshot_series": [],
}


def test_page_ritmo_section_and_news_detail_render_svg_and_alerts(site, page_of):
    # Keyword search must never show Ritmo
    kw = _result(site, mode="keyword", query="standing desk", page=None, ritmo=SAMPLE_RITMO)
    page = page_of("it", kw)
    page.click("[data-action=rtab][data-value=seismo]")
    assert _count(page, ".ritmo-sec") == 0
    assert _count(page, ".ritmo-locked") == 1

    # Company mode renders Ritmo in IT/Light and EN/Dark with 9 bars, alert callout, In breve & ? popovers
    comp = _result(site, ritmo=SAMPLE_RITMO)
    for lang, expected_alert, expected_little in (("it", "Picco reale", "In equilibrio"),
                                                  ("en", "Real spike", "Balanced")):
        page = page_of(lang, comp)
        if lang == "en":
            page.click(".topbar [data-action=theme][data-value=dark]")
        page.click("[data-action=rtab][data-value=seismo]")
        sec = page.locator(".ritmo-sec")
        assert sec.is_visible()
        sec_text = sec.inner_text()
        assert expected_alert in sec_text and expected_little in sec_text and "901" in sec_text
        assert _count(page, ".ritmo-alert") == 1
        assert _count(page, ".ritmo-chart svg rect") == 9
        assert "ritmo" in page.inner_text(".tldr").casefold()

        # Check every ? popover inside .ritmo-sec stays within 1440px viewport and closes on Escape
        help_count = page.locator(".ritmo-sec [data-action=help-toggle]").count()
        assert help_count >= 4
        for idx in range(help_count):
            page.locator(".ritmo-sec [data-action=help-toggle]").nth(idx).click()
            pop = page.locator(".help-wrap.open .help-pop")
            assert pop.is_visible()
            box = pop.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= 1440
            page.keyboard.press("Escape")
            assert _count(page, ".help-wrap.open") == 0

    # Novita view for company changes containing `ritmo` renders .ritmo-sec without a manual refresh button
    page = page_of("it")
    key = f"company:IT:{PAGE_ID}"
    page.route("**/api/history", lambda route: route.fulfill(json={"subjects": [{
        "key": key, "mode": "company", "label": "Kingshot", "country": "IT", "page_id": PAGE_ID,
        "snapshots": 3, "last_taken_at": "2026-11-13T10:00:00+00:00", "active_ads": 194,
    }]}))
    page.route("**/api/history/changes*", lambda route: route.fulfill(json={
        "available": True,
        "subject": {"key": key, "mode": "company", "label": "Kingshot", "country": "IT", "page_id": PAGE_ID},
        "previous": {"taken_at": "2026-10-14T10:00:00+00:00", "active_ads": 180, "ads_loaded": 180},
        "current": {"taken_at": "2026-11-13T10:00:00+00:00", "active_ads": 194, "ads_loaded": 194},
        "days_between": 30.0,
        "sample": False,
        "counts": {"new": 0, "new_texts": 0, "stopped": 0, "changed": 0},
        "new": [],
        "stopped": [],
        "changed": [],
        "ritmo": SAMPLE_RITMO,
    }))
    page.click(".topbar [data-action=mode][data-value=news]")
    page.wait_for_selector("[data-action=news-open]")
    page.click("[data-action=news-open]")
    page.wait_for_selector(".ritmo-sec")
    assert _count(page, ".ritmo-chart svg rect") == 9
    assert _count(page, ".ritmo-alert") == 1
    assert _count(page, ".ritmo-sec [data-action=ritmo-refresh]") == 0


def _sample_struttura(lead_id: str) -> dict:
    return {
        "available": True,
        "mode": "company",
        "sample_scope": "company",
        "country": "IT",
        "concepts_total": 10,
        "reach_concentration": {
            "measurable": True, "scope": "market", "country": "IT", "concepts_with_reach": 5,
            "total_read_reach": 100000, "top1_share": 0.60, "top3_share": 0.90, "top20pct_share": 0.60,
            "hhi": 0.41, "normalized_hhi": 0.26, "effective_n": 2.4, "gini": 0.52, "level": "concentrated",
            "leaders": [{"library_id": lead_id, "share": 0.60, "reach": 60000, "cards_read": 1, "cards": 1}],
        },
        "copy_families": {
            "measurable": True, "evaluated": 8, "total_with_text": 8, "capped": False, "threshold": 0.62,
            "families_count": 3, "diversity_ratio": 0.38, "largest_family_share": 0.50, "median_pairwise_ncd": 0.71,
            "top_families": [{"representative_id": lead_id, "size": 4, "share": 0.50, "opening": "Sample lead family", "member_ids": [lead_id]}],
        },
        "shannon": {
            "formats": {"measurable": True, "items": 8, "categories": 2, "entropy_bits": 0.81, "effective_k": 1.75, "evenness": 0.81, "dominant": "video", "dominant_share": 0.75, "label": "balanced"},
            "destinations": {"measurable": True, "items": 8, "categories": 2, "entropy_bits": 0.81, "effective_k": 1.75, "evenness": 0.81, "dominant": "example.com", "dominant_share": 0.75, "label": "balanced"},
        },
        "audience_drift": {"measurable": False, "reason": "too_few_snapshots_with_audience", "snapshots_with_audience": 1},
    }


def _sample_anomalie(lead_id: str) -> dict:
    return {
        "available": True, "mode": "company", "sample_scope": "company", "concepts_checked": 10, "active_checked": 9, "status": "flagged",
        "baselines": {"median_days": 30.0, "median_reach_per_day": 500.0, "median_body_chars": 150.0, "reach_peers": 6},
        "items": [{
            "library_id": lead_id, "kind": "long_live_low_reach", "kinds": ["long_live_low_reach"], "lenses": ["reach", "copy"],
            "strength": 4.2, "opening": "Quiet evergreen concept",
            "detail": "90d on air vs 30d median, yet only 80/day vs 500/day median",
            "metrics": {"days_running": 90, "reach_per_day": 80, "creatives": 2, "body_chars": 140, "impression_rank": 4, "media_type": "video"},
        }],
    }


SAMPLE_PIANKA = {
    "measurable": True, "overlap": 0.78, "band": "moderate", "ads_a": 4, "ads_b": 3,
    "total_reach_a": 50000, "total_reach_b": 40000,
    "shared_segments": [{"country": "IT", "age_range": "25-34", "gender": "female", "share_a": 0.45, "share_b": 0.40}],
    "distinct_a": [{"country": "IT", "age_range": "18-24", "gender": "male", "share_a": 0.30, "share_b": 0.10, "gap": 0.20}],
    "distinct_b": [{"country": "IT", "age_range": "45-54", "gender": "female", "share_a": 0.08, "share_b": 0.35, "gap": 0.27}],
}

SAMPLE_JS_DRIFT = {
    "measurable": True, "js_distance": 0.24, "js_divergence": 0.058, "state": "drifting",
    "top_gainers": [{"country": "IT", "age_range": "35-44", "gender": "female", "before": 0.12, "after": 0.24, "delta": 0.12}],
    "top_losers": [], "days_between": 14.0, "ads_before": 4, "ads_after": 5, "snapshots_with_audience": 2,
}


def test_page_struttura_anomalie_pianka_and_js_drift(site, page_of):
    base = _result(site)
    lead_id = base["ads"][0]["library_id"]
    comp = _result(site, struttura=_sample_struttura(lead_id), anomalie=_sample_anomalie(lead_id))

    for lang, expected_fam, expected_anom in (("it", "3 famiglie", "Annunci fuori schema"),
                                              ("en", "3 copy families", "Out-of-pattern ads")):
        page = page_of(lang, comp)
        if lang == "en":
            page.click(".topbar [data-action=theme][data-value=dark]")
        page.click("[data-action=rtab][data-value=structure]")
        assert page.locator(".struttura-sec").is_visible()
        assert page.locator(".anomalie-sec").is_visible()
        assert expected_fam in page.inner_text(".struttura-sec") or expected_fam in page.inner_text(".tldr")
        assert expected_anom in page.inner_text(".anomalie-sec")

        # Every ? popover inside .struttura-sec and .anomalie-sec stays in 1440px viewport & closes on Escape
        for sel in (".struttura-sec [data-action=help-toggle]", ".anomalie-sec [data-action=help-toggle]"):
            cnt = page.locator(sel).count()
            assert cnt >= 1
            for idx in range(cnt):
                page.locator(sel).nth(idx).click()
                pop = page.locator(".help-wrap.open .help-pop")
                assert pop.is_visible()
                box = pop.bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= 1440
                page.keyboard.press("Escape")
                assert _count(page, ".help-wrap.open") == 0

    # Clicking an anomaly card opens the ad drawer cleanly
    page = page_of("it", comp)
    page.click("[data-action=rtab][data-value=structure]")
    page.locator(".anom-card").first.click()
    page.wait_for_selector(".drawer")
    assert _count(page, ".drawer") == 1
    page.keyboard.press("Escape")
    assert _count(page, ".drawer") == 0

    # Keyword mode ALSO renders .struttura-sec and .anomalie-sec with sample label
    kw_str = {**_sample_struttura(lead_id), "mode": "keyword", "sample_scope": "keyword_sample"}
    kw_anom = {**_sample_anomalie(lead_id), "mode": "keyword", "sample_scope": "keyword_sample"}
    kw = _result(site, mode="keyword", query="standing desk", page=None, struttura=kw_str, anomalie=kw_anom)
    page = page_of("it", kw)
    page.click("[data-action=rtab][data-value=structure]")
    assert "parola chiave" in page.inner_text(".struttura-sec").casefold()
    assert "parola chiave" in page.inner_text(".anomalie-sec").casefold()

    # Compare sheet renders Pianka section + updates buildCompareBrief
    page = page_of("it")
    cmp_payload = {
        "mode": "compare", "country": "IT",
        "sides": [base, {**base, "page": {**base["page"], "name": "Beta Co"}}],
        "comparison": {
            "names": {"a": "Kingshot", "b": "Beta Co"},
            "country": "IT", "rows": [], "highlights": [],
            "audience_overlap": SAMPLE_PIANKA, "note": "Note",
        },
    }
    page.evaluate("""(r) => { S.mode = 'compare'; S.result = r; S.resultMode = 'compare'; S.cmp = null; render(); }""", cmp_payload)
    page.wait_for_selector(".pianka-sec")
    assert "78%" in page.inner_text(".pianka-sec")
    assert "Pianka" in page.evaluate("buildCompareBrief(S.result)")

    # Novita view renders JS drift bar when /api/history/changes includes audience_drift
    page = page_of("it")
    key = f"company:IT:{PAGE_ID}"
    page.route("**/api/history", lambda route: route.fulfill(json={"subjects": [{
        "key": key, "mode": "company", "label": "Kingshot", "country": "IT", "page_id": PAGE_ID,
        "snapshots": 3, "last_taken_at": "2026-11-13T10:00:00+00:00", "active_ads": 194,
    }]}))
    page.route("**/api/history/changes*", lambda route: route.fulfill(json={
        "available": True,
        "subject": {"key": key, "mode": "company", "label": "Kingshot", "country": "IT", "page_id": PAGE_ID},
        "previous": {"taken_at": "2026-10-30T10:00:00+00:00", "active_ads": 180, "ads_loaded": 180},
        "current": {"taken_at": "2026-11-13T10:00:00+00:00", "active_ads": 194, "ads_loaded": 194},
        "days_between": 14.0, "sample": False,
        "counts": {"new": 0, "new_texts": 0, "stopped": 0, "changed": 0},
        "new": [], "stopped": [], "changed": [],
        "audience_drift": SAMPLE_JS_DRIFT,
    }))
    page.click(".topbar [data-action=mode][data-value=news]")
    page.wait_for_selector("[data-action=news-open]")
    page.click("[data-action=news-open]")
    page.wait_for_selector(".js-drift-bar")
    assert "In spostamento" in page.inner_text(".js-drift-bar")


def test_page_mobile_layout_has_no_overflow_and_clamps_popovers(site, page_of):
    base = _result(site)
    lead_id = base["ads"][0]["library_id"]
    comp = _result(site, struttura=_sample_struttura(lead_id), anomalie=_sample_anomalie(lead_id), durata=SAMPLE_DURATA, ritmo=SAMPLE_RITMO)
    page = page_of("it", comp)
    page.set_viewport_size({"width": 420, "height": 900})
    for tab in ("overview", "ads", "seismo", "durata", "structure", "strategy"):
        page.click(f"[data-action=rtab][data-value={tab}]")
        assert page.evaluate("() => document.documentElement.scrollWidth <= 420"), tab

    page.click("[data-action=rtab][data-value=strategy]")
    page.wait_for_selector(".arch-schema")
    arch_cnt = page.locator(".arch-schema [data-action=help-toggle]").count()
    assert arch_cnt >= 4
    for idx in range(arch_cnt):
        btn = page.locator(".arch-schema [data-action=help-toggle]").nth(idx)
        btn.scroll_into_view_if_needed()
        btn.click()
        pop = page.locator(".help-wrap.open .help-pop")
        assert pop.is_visible()
        box = pop.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 420
        page.keyboard.press("Escape")

    page.click("[data-action=rtab][data-value=structure]")
    page.wait_for_selector(".struttura-sec")
    for sel in (".struttura-sec [data-action=help-toggle]", ".anomalie-sec [data-action=help-toggle]"):
        cnt = page.locator(sel).count()
        assert cnt >= 1
        for idx in range(cnt):
            btn = page.locator(sel).nth(idx)
            btn.scroll_into_view_if_needed()
            btn.click()
            pop = page.locator(".help-wrap.open .help-pop")
            assert pop.is_visible()
            box = pop.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= 420
            page.keyboard.press("Escape")

    page.click("[data-action=rtab][data-value=ads]")
    page.wait_for_selector("table.ads")
    cnt = page.locator("table.ads thead [data-action=help-toggle]").count()
    assert cnt >= 1
    for idx in range(cnt):
        btn = page.locator("table.ads thead [data-action=help-toggle]").nth(idx)
        btn.scroll_into_view_if_needed()
        btn.click()
        pop = page.locator(".help-wrap.open .help-pop")
        assert pop.is_visible()
        box = pop.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 420
        page.keyboard.press("Escape")


def test_page_v05_i18n_singulars_currency_and_popover_scroll(site, page_of):
    base = _result(site)
    lead_id = base["ads"][0]["library_id"]
    anom = _sample_anomalie(lead_id)
    anom["items"][0]["metrics"]["days_running"] = 1
    anom["items"][0]["metrics"]["creatives"] = 1
    strutt = _sample_struttura(lead_id)
    strutt["copy_families"]["top_families"][0]["size"] = 1
    rit = {**SAMPLE_RITMO, "snapshots": 1}

    comp = _result(site, struttura=strutt, anomalie=anom, ritmo=rit)
    page = page_of("it", comp)
    assert "1 annuncio in contrasto" in page.inner_text(".tldr")

    # 1. Localized Italian Annunci fuori schema detail + singulars across tabs
    page.click("[data-action=rtab][data-value=structure]")
    page.wait_for_selector(".anomalie-sec")
    detail = page.inner_text(".anom-detail")
    assert "al giorno" in detail and "mediana" in detail
    assert "on air" not in detail and "/day" not in detail
    meta = page.inner_text(".anom-meta")
    assert "1 giorno" in meta and "1 creativit" in meta
    assert "1 testo (" in page.inner_text(".fam-chip")

    # 2. Scrolling closes open help popover instead of leaving it detached
    page.set_viewport_size({"width": 1440, "height": 500})
    btn = page.locator(".anomalie-sec [data-action=help-toggle]").first
    btn.scroll_into_view_if_needed()
    btn.click()
    assert _count(page, ".help-wrap.open") == 1
    page.evaluate("() => window.scrollBy(0, -180)")
    page.wait_for_function("() => document.querySelectorAll('.help-wrap.open').length === 0")
    page.set_viewport_size({"width": 1440, "height": 900})

    page.click("[data-action=rtab][data-value=seismo]")
    assert "1 snapshot salvato" in page.inner_text(".ritmo-note")

    # 3. Search input widened so English/Italian placeholder is not truncated
    page.click("[data-action=rtab][data-value=ads]")
    assert page.evaluate("() => document.querySelector('.tbl-search').getBoundingClientRect().width") >= 225

    # 4. gender.unknown localizes in both IT and EN compare segments
    pianka_unk = {
        **SAMPLE_PIANKA,
        "shared_segments": [{"country": "US", "age_range": "25-34", "gender": "unknown", "share_a": 0.45, "share_b": 0.40}],
    }
    cmp_payload = {
        "mode": "compare", "country": "US",
        "sides": [base, {**base, "page": {**base["page"], "name": "Beta Co"}}],
        "comparison": {
            "names": {"a": "Kingshot", "b": "Beta Co"},
            "country": "US", "rows": [], "highlights": [],
            "audience_overlap": pianka_unk, "note": "Note",
        },
    }
    page.evaluate("""(r) => { S.mode = 'compare'; S.result = r; S.resultMode = 'compare'; S.cmp = null; render(); }""", cmp_payload)
    page.wait_for_selector(".pianka-sec")
    assert "Non indicato" in page.inner_text(".pianka-sec")
    page.click(".topbar [data-action=lang][data-value=en]")
    assert "Unknown" in page.inner_text(".pianka-sec")

    # 5. Precheck simulator shows € for Eurozone markets (IT) and omits € for non-EUR markets (US)
    page = page_of("it")
    page.click(".lvl-head[data-value=plan]")
    page.wait_for_selector("#sim-cpc-rows")
    assert "€" in page.inner_text("#sim-cpc-rows") and "€" in page.inner_text("#sim-risk-line")
    page.evaluate("() => { S.project = { ...(S.project || {}), market: 'US' }; S.simItFee = false; render(); }")
    page.wait_for_selector("#sim-cpc-rows")
    assert "€" not in page.inner_text("#sim-cpc-rows") and "€" not in page.inner_text("#sim-risk-line")


def test_studio_five_tabs_keyboard_collapse_and_grid_view(site, page_of):
    res = _result(site, ritmo=SAMPLE_RITMO)
    page = page_of("it", res)
    assert page.is_visible(".search-compact")
    assert _count(page, ".top-card") >= 1

    for key, expected_tab in (("2", "ads"), ("3", "seismo"), ("4", "durata"), ("5", "structure"), ("6", "strategy"), ("1", "overview")):
        page.keyboard.press(key)
        assert page.get_attribute(f"[data-action=rtab][data-value={expected_tab}]", "aria-selected") == "true"

    page.keyboard.press("ArrowRight")
    assert page.get_attribute("[data-action=rtab][data-value=ads]", "aria-selected") == "true"
    page.keyboard.press("ArrowLeft")
    assert page.get_attribute("[data-action=rtab][data-value=overview]", "aria-selected") == "true"

    page.click("[data-action=rtab][data-value=ads]")
    page.click("[data-action=ads-view][data-value=cards]")
    assert _count(page, ".ads-grid .ad-card") >= 1
    page.locator(".ads-grid .ad-card").first.click()
    page.wait_for_selector(".drawer")
    first_id = page.evaluate("S.overlay.id")
    page.click("[data-action=ad-step][data-value='1']")
    if len(res["ads"]) > 1:
        assert page.evaluate("S.overlay.id") != first_id
    page.keyboard.press("Escape")

    page.keyboard.press("/")
    page.wait_for_selector("#search input[type=text]")
    assert page.evaluate("document.activeElement === document.querySelector('#search input[type=text]')")


def test_in_page_ai_runner_and_video_hook_inspection(site, page_of):
    res = _result(site)
    lead_id = "123456789012"
    res["ads"][0]["library_id"] = lead_id
    res["ads"][0]["media_type"] = "video"
    page = page_of("en", res, link=(READY, "connected"))

    posted_ai = []
    page.route("**/api/ai/run", lambda route: (
        posted_ai.append({"headers": route.request.headers, "body": json.loads(route.request.post_data)}),
        route.fulfill(status=202, json={"id": "ai1", "status": "running", "folder_name": "pack-1", "level": "analysis"}),
    ))
    page.route("**/api/ai/jobs/ai1", lambda route: route.fulfill(json={
        "id": "ai1",
        "status": "done",
        "folder_name": "pack-1",
        "markdown": f"## Diagnosis\n<script>window.__xss=1</script>\nLead concept {lead_id} dominates.",
        "audit": {"status": "ok", "checked_ad_ids": [lead_id], "warning_count": 0, "warnings": []},
    }))

    page.click("[data-action=rtab][data-value=strategy]")
    page.wait_for_function("!document.querySelector('[data-action=ai-run]').disabled")
    page.click("[data-action=ai-run]")
    page.wait_for_selector(".ai-report-view")
    assert len(posted_ai) == 1 and len(posted_ai[0]["headers"]["x-run-token"]) == 32
    assert page.evaluate("Boolean(window.__xss)") is False
    assert _count(page, ".audit-pill.ok") == 1

    page.click(".ai-report-view .id-link")
    page.wait_for_selector(".drawer")

    page.route("**/api/video/inspect", lambda route: route.fulfill(json={
        "ok": True,
        "ad_id": lead_id,
        "duration": 15.2,
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
        "hook_sheet": None,
        "body_sheet": None,
    }))
    page.click("[data-action=video-inspect]")
    page.wait_for_function("document.querySelector('.vid-inspect-box').innerText.includes('9:16')")
    assert "15.2" in page.inner_text(".vid-inspect-box")


def test_v08_zalando_ritmo_preserved_and_strategy_flowchart_popovers(site, page_of):
    comp = _result(site, ritmo=SAMPLE_RITMO)
    page = page_of("it", comp)

    durata_calls = []
    page.route("**/api/durata", lambda route: (
        durata_calls.append(json.loads(route.request.post_data or "{}")),
        route.fulfill(status=202, json={"id": "durjob_partial", "status": "running", "phase": "list"}),
    ))
    page.route("**/api/jobs/durjob_partial", lambda route: route.fulfill(
        json={"id": "durjob_partial", "status": "done", "result": {
            "ok": True,
            "durata": {"available": False, "reason": "partial_list", "loaded_share": 0.57, "window_days": 90},
        }},
    ))

    # Overview renders prominent Hero title and verdict mini-legend
    assert page.locator(".tldr-hero-title").is_visible()
    assert page.locator(".verdict-mini-legend").is_visible()

    # Switching across tabs never triggers automatic /api/durata calls
    for tab in ("seismo", "durata", "ads", "strategy"):
        page.click(f"[data-action=rtab][data-value={tab}]")
    assert durata_calls == []

    # Tab 2 renders open tier panel
    page.click("[data-action=rtab][data-value=ads]")
    assert page.locator(".tier-panel").is_visible()

    # Explicit Durata run returning partial_list must never overwrite active-ads Ritmo
    page.click("[data-action=rtab][data-value=durata]")
    page.click("[data-action=durata-run]")
    page.wait_for_function("document.querySelector('.durata-sec').innerText.includes('57%')")
    assert len(durata_calls) == 1
    page.click("[data-action=rtab][data-value=seismo]")
    assert _count(page, ".ritmo-chart svg rect") == 9

    # Strategy flowchart renders connected SVG connectors and keeps Copy ? popover anchored near button
    page.click("[data-action=rtab][data-value=strategy]")
    page.wait_for_selector(".arch-schema")
    assert page.locator(".arch-schema").is_visible()
    assert _count(page, ".arch-tree-svg") == 2
    btn = page.locator(".arch-node[data-value=copy] [data-action=help-toggle]")
    btn.scroll_into_view_if_needed()
    btn_box = btn.bounding_box()
    btn.click()
    pop = page.locator(".help-wrap.open .help-pop")
    assert pop.is_visible()
    pop_box = pop.bounding_box()
    assert btn_box and pop_box
    assert pop_box["y"] >= 60
    assert abs(pop_box["y"] - btn_box["y"]) < 260


def test_mode_switch_from_compare_never_blanks_company_or_keyword_and_guard_regressions(site, page_of):
    """Switching from Compare to Company/Keyword must expand the search form (never blank screen),
    pressing Enter in #tbl-q must not submit a new search, clicking inside .help-pop must not close it,
    unknown ad IDs must not leave an orphan .scrim, and Tab 6 simulator must update even when #search is open."""
    page = page_of("it")
    page.wait_for_selector("input[data-bind=company]")

    # 1. Populate a completed Compare result
    page.evaluate("""() => {
      const adA = {
        library_id: '111111111111', advertiser: 'Zalando', body: 'Zalando black friday deal',
        media_type: 'video', score: 88, verdict: 'scaling', reliability: 'high', days_running: 14, creatives: 4,
      };
      const adB = {
        library_id: '222222222222', advertiser: 'Tezenis', body: 'Tezenis winter capsule',
        media_type: 'image', score: 71, verdict: 'holding', reliability: 'high', days_running: 30, creatives: 2,
      };
      S.mode = 'compare';
      S.resultMode = 'compare';
      S.company = 'Zalando';
      S.companyB = 'Tezenis';
      S.result = {
        mode: 'compare', country: 'IT',
        sides: [
          { query: 'Zalando', page: { name: 'Zalando', page_id: '111', category: 'Retail', followers: 1000 }, ads_parsed: 5, ads: [adA] },
          { query: 'Tezenis', page: { name: 'Tezenis', page_id: '222', category: 'Retail', followers: 500 }, ads_parsed: 3, ads: [adB] },
        ],
        comparison: {
          names: { a: 'Zalando', b: 'Tezenis' },
          highlights: [],
          rows: [{ group: 'volume', key: 'active_ads', kind: 'number', a: 5, b: 3 }],
          audience_overlap: { measurable: false },
        },
      };
      render();
    }""")
    page.wait_for_selector(".cmphead")

    # 2. Switch Compare -> Company: must show full Company form (NOT collapsed blank screen)
    page.click("[data-action=mode][data-value=company]")
    assert _count(page, ".search-compact") == 0
    assert page.locator("input[data-bind=company]").is_visible()
    assert page.locator("#results").inner_text().strip() == ""

    # 3. Switch Company -> Keyword: must show full Keyword form (NOT collapsed blank screen)
    page.click("[data-action=mode][data-value=keyword]")
    assert _count(page, ".search-compact") == 0
    assert page.locator("input[data-bind=query]").is_visible()
    assert page.locator("#results").inner_text().strip() == ""

    # 4. Switch back -> Compare: comparison sheet restores cleanly
    page.click("[data-action=mode][data-value=compare]")
    assert page.locator(".cmphead").is_visible()

    # 5. Load a Company result and test #tbl-q Enter, .help-pop click, unknown ad ID scrim, and Tab 6 simulator sync
    search_requests = []
    page.route("**/api/pages*", lambda r: (search_requests.append(r.request.url), r.fulfill(status=200, content_type="application/json", body='{"pages":[]}')))
    page.route("**/api/jobs", lambda r: (search_requests.append(r.request.url), r.fulfill(status=200, content_type="application/json", body='{}')))

    page.evaluate("""() => {
      S.mode = 'company';
      S.resultMode = 'company';
      S.level = 'plan';
      S.levelOpen = true;
      S.searchExpandedManual = true;
      S.tab = 'ads';
      S.stratLevel = 'plan';
      S.result = {
        mode: 'company', country: 'IT', ads_parsed: 2, from_cache: false,
        request: { mode: 'company', country: 'IT', level: 'plan', deep: 10, frames: false },
        page: { name: 'Zalando', page_id: '111', category: 'Retail', followers: 1000 },
        signals: {
          active_ads: 2, video_share: 0.5, new_per_week: 2, started_last_30_days: 2, share_started_last_30_days: 1,
          reach: { available: false }, languages: [], platforms: [], buttons: [], destinations: [],
          copy_patterns: { reused_texts: [] },
        },
        ads: [
          { library_id: '111111111111', advertiser: 'Zalando', body: 'Alpha jacket offer', media_type: 'video', score: 88, verdict: 'scaling', reliability: 'high', days_running: 14, creatives: 4 },
          { library_id: '222222222222', advertiser: 'Zalando', body: 'Beta boots promo', media_type: 'image', score: 62, verdict: 'holding', reliability: 'medium', days_running: 25, creatives: 2 },
        ],
      };
      render();
    }""")
    page.wait_for_selector("#tbl-q")
    page.fill("#tbl-q", "Alpha")
    page.press("#tbl-q", "Enter")
    assert search_requests == []
    assert _count(page, "#ads-tbody tr") == 1

    # Clicking an unknown ad ID must NOT leave a dark .scrim blocking the page
    page.evaluate("ACTIONS['open-ad']('999999999999999')")
    assert _count(page, "#overlay .scrim") == 0

    # Tab 6: clicking inside an open .help-pop inside .arch-node must NOT close the popover
    page.click("[data-action=rtab][data-value=strategy]")
    page.wait_for_selector(".arch-schema")
    btn = page.locator(".arch-node[data-value=copy] [data-action=help-toggle]")
    btn.scroll_into_view_if_needed()
    btn.click()
    pop = page.locator(".help-wrap.open .help-pop")
    assert pop.is_visible()
    pop.click()
    assert pop.is_visible()

    # Tab 6 Level 3 simulator updates even when #search is expanded with Level 3 open simultaneously
    tab6_price = page.locator("#results [data-sim=price]")
    tab6_cpa = page.locator("#results [data-sim-out=cpa]")
    before = tab6_cpa.inner_text()
    tab6_price.fill("300")
    after = tab6_cpa.inner_text()
    assert before != after


def test_durata_backend_preserves_and_syncs_ritmo(monkeypatch, tmp_path):
    """Durata returning partial_list must preserve valid active-ads ritmo on both source.result and job.result."""
    from ad_library_insights import service
    from ad_library_insights.client import AdLibraryClient
    from ad_library_insights.web.app import Job

    valid_ritmo = {"available": True, "sta_lta": {"state": "spike", "ratio": 3.08, "weeks": []}}
    partial_durata = {
        "durata": {"available": False, "reason": "partial_list", "loaded_share": 0.57, "window_days": 90},
        "ritmo": {"available": False, "reason": "partial_list", "loaded_share": 0.57},
    }

    async def fake_analyze_durata(*_a, **_k):
        return partial_durata

    monkeypatch.setattr(service, "analyze_durata", fake_analyze_durata)
    asgi = create_app(client=AdLibraryClient(renderer=lambda *_a, **_k: None), home=tmp_path)
    space = asgi.state.workspace
    src = Job(
        id="src1",
        params={"mode": "company", "country": "IT", "page_id": "111"},
        status="done",
        raw={"page": {"page_id": "111"}, "ads": [{"library_id": "1"}], "ritmo": dict(valid_ritmo)},
        result={"page": {"page_id": "111"}, "ads": [{"library_id": "1"}], "ritmo": dict(valid_ritmo)},
    )
    space.jobs[src.id] = src
    with TestClient(asgi) as http:
        res = http.post("/api/durata", json={"page_id": "111", "country": "IT", "window_days": 90})
        assert res.status_code == 202
        jid = res.json()["id"]
        djob = None
        for _ in range(50):
            djob = http.get(f"/api/jobs/{jid}").json()
            if djob["status"] != "running":
                break
            time.sleep(0.05)

    assert djob["status"] == "done"
    assert src.result["ritmo"]["available"] is True
    assert djob["result"]["ritmo"]["available"] is True
    assert djob["result"]["durata"]["reason"] == "partial_list"


def test_ai_run_rejects_second_concurrent_run_with_409(tmp_path):
    """Only one Claude Code CLI run may be active at a time in Workspace."""
    from ad_library_insights.client import AdLibraryClient
    from ad_library_insights.web.app import Job

    asgi = create_app(client=AdLibraryClient(renderer=lambda *_a, **_k: None), home=tmp_path)
    space = asgi.state.workspace
    space.jobs["j1"] = Job(
        id="j1",
        params={"mode": "company", "country": "IT", "page_id": "111", "level": "analysis", "deep": 10, "frames": False},
        status="done",
        raw={"mode": "company", "country": "IT", "ads": [{"library_id": "1"}]},
        result={"mode": "company", "country": "IT", "ads": [{"library_id": "1"}]},
    )
    space.ai_jobs["busy1"] = {"id": "busy1", "status": "running", "level": "analysis"}

    tok = "c" * 32
    headers = {"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin", "X-Run-Token": tok}
    with TestClient(asgi, base_url="http://127.0.0.1:8765") as client:
        res = client.post(
            "/api/ai/run",
            json={"token": tok, "job_id": "j1", "level": "analysis", "ads": 1, "lang": "it"},
            headers=headers,
        )
    assert res.status_code == 409
    assert res.json() == {"error": "already_running"}

