"""The MCP surface, exercised in memory with a fake page renderer (no network)."""
import asyncio
import json
from pathlib import Path

from fastmcp import Client

from ad_library_insights import cli, link, server
from ad_library_insights.browser import PageSnapshot
from ad_library_insights.client import AdLibraryClient

ROOT = Path(__file__).resolve().parents[1]


def call(monkeypatch, cards, tool, arguments):
    async def renderer(url, wait_seconds, scroll_rounds):
        return PageSnapshot(url=url, status_code=403, page_text="~3 results", cards=cards)

    monkeypatch.setattr(server, "_client", AdLibraryClient(renderer=renderer))

    async def run():
        async with Client(server.mcp) as client:
            return (await client.call_tool(tool, arguments)).data

    return asyncio.run(run())


def test_tools_are_registered():
    async def names():
        async with Client(server.mcp) as client:
            return {tool.name for tool in await client.list_tools()}

    assert asyncio.run(names()) == {"search_ads", "scrape_library_url", "analyze_top_ads",
                                    "export_report", "check_breakeven_cpa", "check_report",
                                    "find_advertiser_pages", "analyze_company",
                                    "what_changed", "estimate_consumption", "prepare_analysis",
                                    "get_project", "save_project", "compare_companies",
                                    "inspect_video", "open_studio", "app_studio_action"}


def test_search_ads_returns_ranked_ads(monkeypatch, cards):
    data = call(monkeypatch, cards, "search_ads", {"country": "de", "query": "standing desk"})
    assert data["ok"] and data["country"] == "DE" and data["distinct_ads"] == 2
    scores = [ad["score"] for ad in data["ads"]]
    assert scores == sorted(scores, reverse=True)


def test_search_ads_by_advertiser_only_and_bad_input(monkeypatch, cards):
    data = call(monkeypatch, cards, "search_ads", {"country": "IT", "advertiser": "Aurora"})
    assert data["query"] == "Aurora" and [ad["library_id"] for ad in data["ads"]] == ["1002"]
    assert "error" in call(monkeypatch, cards, "search_ads", {"country": "Italy", "query": "x"})
    assert "error" in call(monkeypatch, cards, "search_ads", {"country": "IT"})
    assert "error" in call(monkeypatch, cards, "scrape_library_url", {"url": "https://example.com"})


def test_analyze_top_ads(monkeypatch, cards):
    data = call(monkeypatch, cards, "analyze_top_ads", {"country": "DE", "query": "desk", "top_n": 1})
    assert data["summary"]["ads_analyzed"] == 1
    assert data["ads"][0]["hook"]["type"] == "question"


def test_export_report_writes_files(monkeypatch, cards, tmp_path):
    data = call(monkeypatch, cards, "export_report",
                {"country": "DE", "query": "desk", "output_dir": str(tmp_path)})
    assert data["ok"] and Path(data["files"]["markdown"]).exists() and Path(data["files"]["csv"]).exists()


def test_check_breakeven_cpa(monkeypatch, cards):
    data = call(monkeypatch, cards, "check_breakeven_cpa", {
        "price": 60, "product_cost": 25, "shipping_cost": 5, "multiplier": 2,
        "ads": [{"name": "dead", "spend": 65, "add_to_cart": 0, "purchases": 0},
                {"name": "fine", "spend": 40, "add_to_cart": 3, "purchases": 2}]})
    assert data["breakeven_cpa"] == 30 and data["cut_threshold"] == 60
    assert data["to_cut"] == ["dead"]


def test_nothing_is_hardcoded_to_one_industry():
    """Keyword, advertiser and country are inputs; the shipped code and docs name no niche."""
    banned = ("fitness", "gym", "palestra", "workout")
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("src/**/*.json"), *ROOT.glob("src/**/*.js"),
             *ROOT.glob("skills/**/*.md"), *ROOT.glob(".claude/**/*.md"), ROOT / "README.md"]
    assert files
    for file in files:
        if file.exists():
            text = file.read_text(encoding="utf-8").casefold()
            # the rating guide explains the score with one named example; nothing else may
            text = text.replace("fitnessx - i corsi dei migliori trainer", "")
            assert not [word for word in banned if word in text], file


def test_mcp_app_resource_and_open_studio(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_client", AdLibraryClient(renderer=lambda *_a, **_k: PageSnapshot(url="", status_code=200, page_text="", cards=[])))
    monkeypatch.setattr(server.project, "load", lambda: None)
    monkeypatch.setattr(server.history, "History", lambda: type("H", (), {"subjects": lambda self: []})())

    async def exercise():
        async with Client(server.mcp) as client:
            resources = await client.list_resources()
            by_uri = {str(r.uri): r for r in resources}
            assert "ui://ad-library-insights/studio.html" in by_uri
            assert by_uri["ui://ad-library-insights/studio.html"].mime_type == "text/html;profile=mcp-app"

            contents = await client.read_resource("ui://ad-library-insights/studio.html")
            html = contents[0].text if isinstance(contents, list) else str(contents)
            assert len(html.encode("utf-8")) < 1_048_576
            low = html.lower()
            assert "<!doctype html>" in low
            assert "<script src=" not in low
            assert 'rel="stylesheet"' not in low
            assert "applyDocumentTheme" in html

            opened = (await client.call_tool("open_studio", {})).data
            state = (await client.call_tool("app_studio_action", {"action": "state"})).data
            return opened, state

    opened, state = asyncio.run(exercise())
    assert opened["ok"] is True and opened["view"] == "home"
    assert state["ok"] is True and isinstance(state["deep_choices"], list)


def test_cli_connect_prints_antigravity_config(monkeypatch, tmp_path, capsys):
    (tmp_path / "mcp_config.json").write_text("", encoding="utf-8")
    monkeypatch.setattr(link, "_antigravity_root", lambda: tmp_path)
    rc = cli.main(["connect", "--antigravity"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["antigravity"]["ok"] is True
    assert out["antigravity"]["mcp_config"]["ad-library-insights"]["args"] == ["-m", "ad_library_insights"]
    saved = json.loads((tmp_path / "mcp_config.json").read_text(encoding="utf-8"))
    assert saved["mcpServers"]["ad-library-insights"]["args"] == ["-m", "ad_library_insights"]
    assert (tmp_path / "skills" / "competitor-analysis" / "SKILL.md").is_file()


def test_app_studio_action_compare_and_durata_validation(monkeypatch, cards):
    async def renderer(url, wait_seconds, scroll_rounds):
        return PageSnapshot(url=url, status_code=200, page_text="~2 results", cards=cards)

    monkeypatch.setattr(server, "_client", AdLibraryClient(renderer=renderer))

    async def exercise():
        async with Client(server.mcp) as client:
            bad_pid = (await client.call_tool("app_studio_action", {"action": "durata", "payload": {"page_id": "abc"}})).data
            bad_win = (await client.call_tool("app_studio_action", {"action": "durata", "payload": {"page_id": "111", "window_days": 45}})).data
            same_cmp = (await client.call_tool("app_studio_action", {"action": "compare", "payload": {"page_id": "111", "page_id_b": "111"}})).data
            ok_cmp = (await client.call_tool("app_studio_action", {"action": "compare", "payload": {"page_id": "111", "page_id_b": "222", "country": "DE", "deep": 0}})).data
            return bad_pid, bad_win, same_cmp, ok_cmp

    bad_pid, bad_win, same_cmp, ok_cmp = asyncio.run(exercise())
    assert bad_pid["ok"] is False
    assert bad_win["ok"] is False
    assert same_cmp["ok"] is False
    assert ok_cmp["ok"] is True and ok_cmp["mode"] == "compare" and ok_cmp["comparison"] is not None
    assert len(ok_cmp["sides"]) == 2


def test_ai_runner_handles_missing_binary_oserror_and_success(monkeypatch, tmp_path):
    from ad_library_insights import ai_runner

    monkeypatch.setattr(ai_runner, "_supported_flags", lambda _bin: frozenset())
    monkeypatch.setattr(ai_runner.link, "find_claude", lambda: None)
    assert ai_runner.run_claude_brief("brief", tmp_path)["error"] == "claude_missing"

    assert ai_runner.run_claude_brief("brief", tmp_path / "missing", claude_bin="claude")["error"] == "command_failed"

    def boom(*_a, **_k):
        raise OSError("cannot exec")

    monkeypatch.setattr(ai_runner.subprocess, "Popen", boom)
    res_err = ai_runner.run_claude_brief("brief", tmp_path, claude_bin="claude")
    assert res_err["ok"] is False and res_err["error"] == "command_failed"

    class FakeProc:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            assert input == "hello brief"
            return ("# Final Report\n\nVerified.", "")

    monkeypatch.setattr(ai_runner.subprocess, "Popen", lambda *_a, **_k: FakeProc())
    res_ok = ai_runner.run_claude_brief("hello brief", tmp_path, claude_bin="claude")
    assert res_ok["ok"] is True and "Final Report" in res_ok["markdown"]


def test_ai_runner_enforces_readonly_tools_and_no_user_mcp(monkeypatch, tmp_path):
    from ad_library_insights import ai_runner

    recorded = []

    class CapturingProc:
        returncode = 0

        def __init__(self, cmd):
            self.cmd = cmd

        def communicate(self, input=None, timeout=None):
            return ("# Verified Output", "")

    def fake_popen(cmd, **kwargs):
        recorded.append((list(cmd), kwargs))
        return CapturingProc(cmd)

    monkeypatch.setattr(ai_runner.subprocess, "Popen", fake_popen)

    class FakeHelp:
        def __init__(self, stdout):
            self.stdout = stdout
            self.stderr = ""

    # 1. Modern CLI: --restricted, --permission-prompts, --no-session-persistence supported
    ai_runner._FLAG_CACHE.clear()
    monkeypatch.setattr(
        ai_runner.subprocess,
        "run",
        lambda *_a, **_k: FakeHelp("--restricted\n--permission-prompts\n--no-session-persistence"),
    )
    for lang in ("it", "en"):
        res = ai_runner.run_claude_brief("brief body", tmp_path, lang=lang, claude_bin="modern-claude")
        assert res["ok"] is True

    assert len(recorded) == 2
    for cmd, kwargs in recorded:
        assert kwargs.get("shell") is False
        assert "-p" in cmd
        assert cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"
        assert "--strict-mcp-config" in cmd
        assert cmd[cmd.index("--disallowedTools") + 1] == "mcp__*"
        assert "--restricted" in cmd
        assert cmd[cmd.index("--permission-prompts") + 1] == "none"
        assert "--no-session-persistence" in cmd
        sep = cmd.index("--")
        instruction = cmd[sep + 1]
        assert sep == len(cmd) - 2
        assert "<untrusted_ad_content>" in instruction
        assert "</untrusted_ad_content>" in instruction

    # 2. Older CLI: optional flags absent in --help are omitted cleanly
    recorded.clear()
    monkeypatch.setattr(ai_runner.subprocess, "run", lambda *_a, **_k: FakeHelp("Usage: claude [options]"))
    res_old = ai_runner.run_claude_brief("brief body", tmp_path, lang="en", claude_bin="legacy-claude")
    assert res_old["ok"] is True
    old_cmd = recorded[0][0]
    assert old_cmd[old_cmd.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--strict-mcp-config" in old_cmd
    assert old_cmd[old_cmd.index("--disallowedTools") + 1] == "mcp__*"
    assert "--restricted" not in old_cmd
    assert "--permission-prompts" not in old_cmd
    assert "--no-session-persistence" not in old_cmd
    ai_runner._FLAG_CACHE.clear()


