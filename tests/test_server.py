"""The MCP surface, exercised in memory with a fake page renderer (no network)."""
import asyncio
from pathlib import Path

from fastmcp import Client

from ad_library_insights import server
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
                                    "export_report", "check_breakeven_cpa",
                                    "find_advertiser_pages", "analyze_company",
                                    "what_changed", "estimate_consumption", "prepare_analysis",
                                    "get_project", "save_project", "compare_companies"}


def test_search_ads_returns_ranked_ads(monkeypatch, cards):
    data = call(monkeypatch, cards, "search_ads", {"country": "de", "query": "standing desk"})
    assert data["ok"] and data["country"] == "DE" and data["distinct_ads"] == 2
    scores = [ad["longevity_score"] for ad in data["ads"]]
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
