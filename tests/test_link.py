"""The connection to Claude Code: a fake `claude` program stands in for the real one.

Nothing here touches the real Claude Code configuration or skills folder: the fake keeps its own
state in a temporary folder and the skills are copied between two temporary folders.
"""
import json
import os
import secrets
import stat
import sys
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ad_library_insights import link
from ad_library_insights.web.app import create_app
from test_company import Studio

FAKE = '''
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
state_file = os.environ["FAKE_CLAUDE_STATE"]
servers = json.load(open(state_file)) if os.path.exists(state_file) else []
mode = os.environ.get("FAKE_CLAUDE_MODE", "")
if args[:2] == ["mcp", "list"]:
    if mode == "list_fail":
        sys.exit(1)
    if mode == "list_slow":
        time.sleep(1.5)
    print("Checking MCP server health...")
    for name in servers:
        print(name + ": some command - Connected")
    sys.exit(0)
if args[:2] == ["mcp", "add"]:
    if mode == "add_fail":
        print("boom: could not write the configuration", file=sys.stderr)
        sys.exit(1)
    if args[2] in servers:
        print("MCP server " + args[2] + " already exists in user config", file=sys.stderr)
        sys.exit(1)
    servers.append(args[2])
    json.dump(servers, open(state_file, "w"))
    sys.exit(0)
sys.exit(2)
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A `claude` on PATH, its call log and its state, and settings that point at temporary folders."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "fake_claude.py").write_text(FAKE, encoding="utf-8")
    if sys.platform.startswith("win"):
        (bin_dir / "claude.bat").write_text(f'@"{sys.executable}" "%~dp0fake_claude.py" %*\r\n')
    else:
        launcher = bin_dir / "claude"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake_claude.py" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    log, state = tmp_path / "calls.log", tmp_path / "servers.json"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLAUDE_STATE", str(state))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    source = tmp_path / "skills-source"
    for skill in ("alpha", "beta"):
        (source / skill / "references").mkdir(parents=True)
        (source / skill / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
        (source / skill / "references" / "note.md").write_text(f"notes of {skill}\n", encoding="utf-8")
    settings = link.Settings(skills_source=source, skills_target=tmp_path / "user-skills",
                             python=str(tmp_path / "a folder with spaces" / "python.exe"),
                             mcp_timeout=0.4)

    def calls():
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    return type("Fake", (), {"settings": settings, "calls": staticmethod(calls), "state": state,
                             "log": log, "tmp": tmp_path, "monkeypatch": monkeypatch})


@pytest.fixture
def client(fake):
    studio = Studio(fake.tmp)
    with TestClient(create_app(studio.client, home=fake.tmp / "home", connection=fake.settings),
                    base_url="http://127.0.0.1:8765") as page:
        yield page


def connect(client, token=None, overwrite=False, **headers):
    token = token or secrets.token_hex(16)
    sent = {"Origin": "http://127.0.0.1:8765", "X-Link-Token": token, **headers}
    sent = {k: v for k, v in sent.items() if v is not None}
    return client.post("/api/link/connect", json={"token": token, "overwrite_skills": overwrite}, headers=sent)


ADD = ["mcp", "add", "ad-library-insights", "--scope", "user", "--"]


def test_connecting_runs_the_exact_command_as_a_list_and_copies_the_skills(client, fake):
    answer = connect(client)
    assert answer.status_code == 200
    body = answer.json()
    assert body["ok"] and body["server"] == "added" and body["skills"] == {"copied": 4, "kept": []}
    added = [call for call in fake.calls() if call[:2] == ["mcp", "add"]]
    # the interpreter path has spaces and stays one argument; nothing is split or quoted by a shell
    assert added == [ADD + [fake.settings.python, "-m", "ad_library_insights"]]
    assert json.loads(fake.state.read_text()) == ["ad-library-insights"]
    target = fake.settings.skills_target
    assert (target / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "# alpha\n"
    assert (target / "beta" / "references" / "note.md").is_file()


def test_the_command_shown_matches_the_one_run(client, fake):
    shown = client.get("/api/link/status").json()["command"]
    assert shown.startswith("claude mcp add ad-library-insights --scope user -- ")
    assert "a folder with spaces" in shown
    assert ('"' if sys.platform.startswith("win") else "'") in shown            # quoted for a shell
    assert shown.endswith("-m ad_library_insights")


def test_a_failing_command_is_reported_and_copies_nothing(client, fake):
    fake.monkeypatch.setenv("FAKE_CLAUDE_MODE", "add_fail")
    answer = connect(client)
    body = answer.json()
    assert answer.status_code == 500 and body["error"] == "command_failed" and "boom" in body["detail"]
    assert not fake.settings.skills_target.exists()


def test_connecting_twice_says_it_is_already_done_and_does_not_redo_it(client, fake):
    assert connect(client).json()["server"] == "added"
    again = connect(client).json()
    assert again["ok"] and again["server"] == "already" and again["skills"] == {"copied": 0, "kept": []}
    assert len([call for call in fake.calls() if call[:2] == ["mcp", "add"]]) == 1


def test_a_server_that_exists_but_cannot_be_listed_still_counts_as_already_connected(client, fake):
    fake.state.write_text(json.dumps(["ad-library-insights"]))
    fake.monkeypatch.setenv("FAKE_CLAUDE_MODE", "list_fail")          # the check fails, the add says "exists"
    body = connect(client).json()
    assert body["ok"] and body["server"] == "already"


def test_without_claude_code_the_page_gets_a_clear_answer(client, fake):
    empty = fake.tmp / "empty"
    empty.mkdir()
    fake.monkeypatch.setenv("PATH", str(empty))
    assert client.get("/api/link/status").json()["claude"] is False
    assert client.get("/api/link/mcp").json() == {"state": "no_claude"}
    answer = connect(client)
    assert answer.status_code == 500 and answer.json()["error"] == "claude_missing"
    assert fake.calls() == [] and not fake.settings.skills_target.exists()


def test_a_request_from_another_origin_is_refused_and_runs_nothing(client, fake):
    token = secrets.token_hex(16)
    for headers in ({"Origin": "https://evil.example"}, {"Origin": "http://localhost:8765"},
                    {"Origin": "http://127.0.0.1:9999"}, {"Origin": None}):
        assert connect(client, token, **headers).status_code == 403
    assert fake.calls() == [] and not fake.settings.skills_target.exists()


def test_a_request_with_another_host_is_refused(fake):
    studio = Studio(fake.tmp)
    for base in ("http://testserver", "http://localhost:8765", "http://192.168.1.5:8765"):
        with TestClient(create_app(studio.client, home=fake.tmp / "home", connection=fake.settings),
                        base_url=base) as page:
            token = secrets.token_hex(16)
            answer = page.post("/api/link/connect", json={"token": token},
                               headers={"Origin": base, "X-Link-Token": token})
            assert answer.status_code == 403, base
    assert fake.calls() == []


def test_the_confirmation_token_is_required_matching_and_used_once(client, fake):
    token = secrets.token_hex(16)
    assert connect(client, token, **{"X-Link-Token": None}).status_code == 403       # no header
    assert connect(client, token, **{"X-Link-Token": secrets.token_hex(16)}).status_code == 403   # different
    assert connect(client, "short").status_code == 403                                # too short
    assert connect(client, "Z" * 32).status_code == 403                               # not hex
    assert fake.calls() == []
    assert connect(client, token).status_code == 200
    assert connect(client, token).status_code == 403                                  # reused
    plain = client.post("/api/link/connect", content=b'{"token": "x"}',
                        headers={"Origin": "http://127.0.0.1:8765", "Content-Type": "text/plain"})
    assert plain.status_code == 400
    assert client.post("/api/link/connect", content=b"not json", headers={
        "Origin": "http://127.0.0.1:8765", "Content-Type": "application/json"}).status_code == 403


def test_a_skill_file_the_user_changed_is_kept_until_they_say_to_replace_it(client, fake):
    assert connect(client).json()["skills"]["copied"] == 4
    mine = fake.settings.skills_target / "alpha" / "SKILL.md"
    mine.write_text("my own words\n", encoding="utf-8")
    kept = connect(client).json()
    assert kept["skills"] == {"copied": 0, "kept": ["alpha/SKILL.md"]}
    assert mine.read_text(encoding="utf-8") == "my own words\n"
    assert client.get("/api/link/status").json()["skills"]["modified"] == ["alpha/SKILL.md"]
    replaced = connect(client, overwrite=True).json()
    assert replaced["skills"] == {"copied": 1, "kept": []}
    assert mine.read_text(encoding="utf-8") == "# alpha\n"


def test_status_tells_what_is_in_place_and_the_slow_check_is_separate(client, fake):
    quick = client.get("/api/link/status").json()
    assert quick["claude"] is True and quick["skills"]["installed"] is False
    assert quick["skills"]["total"] == 4 and quick["skills_folder"] == "~/.claude/skills"
    assert fake.calls() == []                                    # the quick part runs no command
    assert client.get("/api/link/mcp").json() == {"state": "missing"}
    connect(client)
    assert client.get("/api/link/mcp").json() == {"state": "connected"}
    assert client.get("/api/link/status").json()["skills"]["installed"] is True


def test_the_slow_check_gives_up_instead_of_hanging(client, fake):
    fake.monkeypatch.setenv("FAKE_CLAUDE_MODE", "list_fail")
    assert client.get("/api/link/mcp").json() == {"state": "unknown"}
    fake.monkeypatch.setenv("FAKE_CLAUDE_MODE", "list_slow")
    started = time.time()
    assert client.get("/api/link/mcp").json() == {"state": "unknown"}
    assert time.time() - started < 10


def test_texts_of_the_connection_never_use_the_words_kept_out_of_the_page():
    from ad_library_insights.web.app import STATIC
    strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
    banned = {"it": ("pesant", "limit", "consum"), "en": ("heavy", "limit", "usage", "consum")}
    for language, words in banned.items():
        for key, value in strings[language].items():
            if key.startswith(("lv.", "link.", "way.", "how.")):
                assert not any(word in value.lower() for word in words), (language, key)
                assert "—" not in value and "–" not in value, (language, key)    # no long dashes


def test_connecting_also_copies_specialist_sub_agents_when_present(tmp_path):
    skills_src, skills_dst = tmp_path / "skills", tmp_path / "user" / "skills"
    agents_src, agents_dst = tmp_path / ".claude" / "agents", tmp_path / "user" / "agents"
    (skills_src / "alpha").mkdir(parents=True)
    (skills_src / "alpha" / "SKILL.md").write_text("# alpha\n", encoding="utf-8")
    agents_src.mkdir(parents=True)
    (agents_src / "ad-copy-analyst.md").write_text("# copy specialist\n", encoding="utf-8")
    before = link.skills_state(skills_src, skills_dst, agents_src, agents_dst)
    assert before["total"] == 2 and before["missing"] == 2 and not before["installed"]
    done = link.install_skills(skills_src, skills_dst, False, agents_src, agents_dst)
    assert done == {"copied": 2, "kept": []}
    assert (agents_dst / "ad-copy-analyst.md").read_text(encoding="utf-8") == "# copy specialist\n"
    after = link.skills_state(skills_src, skills_dst, agents_src, agents_dst)
    assert after["installed"] and after["missing"] == 0


def test_codex_and_antigravity_helpers_build_commands_and_copy_skills(tmp_path):
    cmd = link.codex_shown_command("/path/to/python")
    assert cmd.startswith("codex mcp add ad-library-insights -- ") and cmd.endswith("-m ad_library_insights")
    entry = link.antigravity_mcp_entry("/path/to/python")
    assert entry == {"ad-library-insights": {"command": "/path/to/python", "args": ["-m", "ad_library_insights"]}}
    src, dst = tmp_path / "skills", tmp_path / "antigravity" / "skills"
    (src / "sk").mkdir(parents=True)
    (src / "sk" / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    copied = link.install_to_folder(src, dst)
    assert copied == {"copied": 1, "kept": []} and (dst / "sk" / "SKILL.md").is_file()


def test_config_fallback_detects_user_and_project_scoped_servers(client, fake):
    fake.monkeypatch.setenv("FAKE_CLAUDE_MODE", "list_fail")
    cfg = fake.settings.claude_config
    assert cfg is not None and not cfg.exists()
    assert client.get("/api/link/mcp").json() == {"state": "unknown"}

    cfg.write_text(json.dumps({"mcpServers": {"ad-library-insights": {"command": "python"}}}), encoding="utf-8")
    assert client.get("/api/link/mcp").json() == {"state": "connected"}

    cfg.write_text(json.dumps({
        "projects": {"C:/repo": {"mcpServers": {"ad-library-insights": {"command": "python"}}}}
    }), encoding="utf-8")
    assert client.get("/api/link/mcp").json() == {"state": "connected"}


def test_tutorial_mentions_only_real_mcp_tools_from_server_py():
    import ast
    import re

    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "src" / "ad_library_insights" / "server.py").read_text(encoding="utf-8"))

    def _is_mcp_tool(dec: ast.expr) -> bool:
        target = dec.func if isinstance(dec, ast.Call) else dec
        return (isinstance(target, ast.Attribute) and target.attr == "tool"
                and isinstance(target.value, ast.Name) and target.value.id == "mcp")

    real_tools = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_mcp_tool(dec) for dec in node.decorator_list)
    }
    assert real_tools

    strings = json.loads(
        (root / "src" / "ad_library_insights" / "web" / "static" / "strings.json").read_text(encoding="utf-8")
    )
    ignored = {"ad_library_insights", "mcp_config"}
    for lang in ("it", "en"):
        assert ".venv/bin/python" in strings[lang]["tut.6.c2.d"]
        assert ".venv/bin/python" in strings[lang]["tut.6.c3.d"]
        assert ".venv\\Scripts\\python.exe" in strings[lang]["tut.6.c2.d"]
        assert ".venv\\Scripts\\python.exe" in strings[lang]["tut.6.c3.d"]
        tut_texts = [v for k, v in strings[lang].items() if k.startswith("tut.")]
        found = [tok for txt in tut_texts for tok in re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", txt) if tok not in ignored]
        assert len(found) >= 5, (lang, found)
        unknown = [tok for tok in found if tok not in real_tools]
        assert not unknown, f"Unknown MCP tool names in {lang} tutorial: {unknown}"


def test_tutorial_mentions_only_real_ui_buttons_and_labels():
    import re

    root = Path(__file__).resolve().parents[1]
    strings = json.loads(
        (root / "src" / "ad_library_insights" / "web" / "static" / "strings.json").read_text(encoding="utf-8")
    )

    forbidden = (
        "Prepara l'analisi / il piano",
        "Prepare brief",
        "Mostra i fotogrammi",
        "Show the stills",
        "Refresh now",
        "Promettente",
        "Promising",
        "<percorso-.venv>",
    )
    assert "<percorso-python-.venv>" in strings["it"]["tut.6.c3.f"]
    assert "<project-.venv-python>" in strings["en"]["tut.6.c3.f"]

    quote_pat = re.compile(r"«([^»]+)»|“([^”]+)”|(?<![A-Za-z])'([^']{3,})'")
    example_ctx = re.compile(r"\((?:es\.|e\.g\.)\s+[^)]*$")
    extras = {
        "it": {"Nuovo", "Alta", "Media", "Bassa"},
        "en": {"New", "High", "Medium", "Low"},
    }

    for lang in ("it", "en"):
        all_tutorial_vals = "\n".join(strings[lang].values())
        for bad in forbidden:
            assert bad not in all_tutorial_vals, f"Forbidden stale label {bad!r} found in {lang}"

        real_ui = {
            v for k, v in strings[lang].items()
            if not k.startswith(("tut.", "kpi.", "how.", "leg.", "guide."))
        }
        multi_title = strings[lang].get("way.multi.title", "")
        if "?" in multi_title:
            real_ui.add(multi_title.split("?", 1)[0] + "?")
        real_ui |= extras[lang]

        for k, txt in strings[lang].items():
            if not k.startswith(("how.", "tut.", "kpi.")):
                continue
            for m in quote_pat.finditer(txt):
                tok = next(g for g in m.groups() if g)
                if "[Brand]" in tok or example_ctx.search(txt[:m.start()]):
                    continue
                assert tok in real_ui, f"Unknown UI label {tok!r} cited in {lang}.{k}"
