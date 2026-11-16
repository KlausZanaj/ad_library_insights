"""The local app, offline: API, consumption estimate, project card, brief, page texts."""
import json
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ad_library_insights import briefs, consumption, project
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
    assert client.put("/api/project", json={"product": "x"}).status_code == 400
    saved = client.put("/api/project", json=CARD).json()["project"]
    assert saved["price"] == 349.0
    assert client.get("/api/project").json()["project"]["market"] == "DE"


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
