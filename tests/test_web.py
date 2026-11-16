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

    def open_page(lang="it", result=None):
        context = site.browser.new_context(viewport={"width": 1440, "height": 900})
        contexts.append(context)
        page = context.new_page()
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
    assert "Copertura letta per 18 concetti" in text and "aprendo 40 annunci" in text
    assert "concetti della classifica" in page.inner_text("#search")
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
        assert one in drawer and wrong not in drawer
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
