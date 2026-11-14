"""Analysis and Plan levels: data packs, briefs, sub-agent and skill files, MCP tools."""
import asyncio
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastmcp import Client

from ad_library_insights import briefs, packs, server, service
from test_company import PAGE_ID, Studio

ROOT = Path(__file__).resolve().parents[1]
CARD = {"product": "Standing desk", "price": 349.0, "product_cost": 120.0, "market": "DE",
        "goal": "30 orders a day", "main_problem": "High cost per purchase"}
TODAY = date(2026, 11, 13)


@pytest.fixture
def company(tmp_path):
    """A company result with reach read for the top three ads and stills saved."""
    studio = Studio(tmp_path)

    async def flow():
        result = await service.research_company(studio.client, "IT", page_id=PAGE_ID, as_of=TODAY)
        return await service.deepen(studio.client, result, 3, frames=True)

    return asyncio.run(flow())


def front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    head, body = text[4:].split("\n---\n", 1)
    fields = dict(re.findall(r"^(\w+):\s*(.*)$", head, flags=re.M))
    return fields, body


# --- numbers --------------------------------------------------------------------------

def test_test_budget_comes_from_break_even():
    numbers = briefs.test_numbers(CARD)
    assert numbers == {"margin": 229.0, "cpa": 229.0, "roas": 1.52, "cut_low": 458.0, "cut_high": 687.0,
                       "per_ad": 572.5, "round_total": 2862.5, "multiplier": 2.5, "ideas": 5}
    with pytest.raises(ValueError):
        briefs.test_numbers({**CARD, "product_cost": 349.0})


# --- data pack ------------------------------------------------------------------------

def test_slices_cover_the_four_lenses(company):
    slices, images = packs.sections(company, ads=3, frames=True)
    assert tuple(slices) == packs.SLICES
    assert "three parts: scale" in slices["overview"] and "Reliability of a rating" in slices["overview"]
    assert "do not count as creatives" in slices["overview"]
    assert "Meta publishes no spend and no sales" in slices["overview"]
    top = company["ads"][0]
    assert f"id {top['library_id']}" in slices["copy"] and "> " in slices["copy"]
    assert "first pass made by rules" in slices["copy"]
    assert "| 835,585 |" in slices["reach"] and "| 7,398,228 | 1,679,270 |" in slices["reach"]    # country first, then EU and UK
    assert "Locations targeted (ads):" in slices["reach"] and "Italy" in slices["reach"]
    assert "Launches per week" in slices["testing"] and "itunes.apple.com" in slices["testing"]
    assert len(images) == 9 and all(Path(p).exists() for p in images)       # three stills for three videos


def test_reach_table_says_which_ads_were_not_read(company):
    company["ads"][-1].pop("reach")                    # as for an ad below the ones opened
    company["ads"][-2]["reach"] = {"available": False}
    slices, _ = packs.sections(company, ads=5)
    assert slices["reach"].count("| not read |") == 1 and slices["reach"].count("| not published |") == 1


def test_without_stills_the_creative_slice_says_so(company):
    slices, images = packs.sections(company, ads=3, frames=False)
    assert "Video stills: not collected for this pack" in slices["creative"]
    assert "thumbnail:" in slices["creative"] and "stills (start" not in slices["creative"]
    assert images == []


def test_pack_is_written_one_file_per_specialist(company, tmp_path):
    made = briefs.prepare("analysis", company, 3, True, lang="en", directory=tmp_path / "packs", today=TODAY)
    folder = Path(made["folder"])
    assert folder.name == "kingshot-it-analysis-2026-11-13"
    assert sorted(p.name for p in folder.iterdir()) == ["brief.md", "copy.md", "creative.md", "manifest.json",
                                                         "overview.md", "reach.md", "testing.md"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "analysis" and manifest["ads"] == 3 and len(manifest["images"]) == 9
    assert (folder / "brief.md").read_text(encoding="utf-8") == made["text"]
    assert "slices" not in made and made["ads"] == 3 and made["frames"] is True


def test_plan_pack_adds_the_project_file(company, tmp_path):
    made = briefs.prepare("plan", company, 3, False, CARD, "it", tmp_path / "packs", TODAY)
    project_file = Path(made["files"]["project"]).read_text(encoding="utf-8")
    assert "Standing desk" in project_file and "572.5" in project_file and "2,862.5" in project_file


# --- briefs ---------------------------------------------------------------------------

def test_analysis_brief_works_in_a_single_pass(company):
    made = briefs.compose("analysis", company, 3, frames=True, lang="en")
    text = made["text"]
    assert "performance marketing specialist" in text and "Do not reason as a social media manager" in text
    for heading in ("### Copy", "### Creative", "### Reach and audience", "### Testing and destinations"):
        assert heading in text
    assert text.count("\n1. ") >= 2 and "finding · evidence" in text
    assert "What this data cannot tell." in text and "Write in English." in text
    assert "## Pictures to attach" in text and len(made["images"]) == 9
    assert made["size"]["tokens"] > made["size"]["tokens_single_pass"]        # re-reads are counted


def test_brief_without_stills_tells_the_assistant(company):
    made = briefs.compose("analysis", company, 3, frames=False, lang="it")
    assert made["images"] == []
    assert "nessuna: scrivi che la lettura delle creatività si basa solo su formati e testi" in made["text"]
    assert "Scrivi in italiano." in made["text"]


def test_plan_brief_starts_from_the_project(company):
    text = briefs.compose("plan", company, 3, project=CARD, lang="en")["text"]
    assert "Act as a head of marketing. Diagnose first, then propose." in text
    assert text.index("## Steps") < text.index("## My project") < text.index("## Numbers for the test") < text.index("## Data")
    assert "Five ad ideas for my product" in text and "Not copies" in text
    assert "Report for whoever decides: one page." in text
    assert "Break-even CPA, the most one purchase may cost in ads: 229" in text
    assert "458 to 687" in text and "up to 572.5" in text and "up to 2,862.5" in text
    assert "the real break-even is lower" in text


def test_plan_is_refused_without_the_project_card(company):
    with pytest.raises(ValueError):
        briefs.compose("plan", company, 3)
    with pytest.raises(ValueError):
        briefs.compose("data", company, 3)


def test_instructions_exist_in_both_languages():
    for lang in ("it", "en"):
        analysis = briefs.instructions("analysis", "Northwind", lang)
        plan = briefs.instructions("plan", "Northwind", lang)
        assert analysis.count("\n4. ") == 2 and "Northwind" in analysis      # four passes, at least four deliverables
        assert plan.count("\n5. ") == 1 and "Northwind" in plan              # five steps
    assert set(briefs._T["it"]) == set(briefs._T["en"])


# --- files for Claude Code ------------------------------------------------------------

AGENTS = {"ad-copy-analyst": "copy.md", "ad-creative-analyst": "creative.md",
          "ad-reach-analyst": "reach.md", "ad-testing-analyst": "testing.md"}


def test_each_specialist_agent_reads_only_its_slice():
    folder = ROOT / ".claude" / "agents"
    assert {p.stem for p in folder.glob("*.md")} == set(AGENTS)
    for name, data_file in AGENTS.items():
        fields, body = front_matter(folder / f"{name}.md")
        assert fields["name"] == name and len(fields["description"]) > 60
        assert "Read" in fields["tools"]
        assert f"`{data_file}`" in body and "`overview.md`" in body
        others = set(AGENTS.values()) - {data_file}
        assert not [other for other in others if f"`{other}`" in body]
        assert "**Strength**" in body and "Never invent" in body
    assert "start, middle" in (folder / "ad-creative-analyst.md").read_text(encoding="utf-8")


def tool_names():
    async def names():
        async with Client(server.mcp) as client:
            return {tool.name for tool in await client.list_tools()}
    return asyncio.run(names())


def test_level_skills_follow_the_format_and_name_real_tools():
    tools = tool_names()
    for name in ("competitor-analysis", "competitor-plan"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith(f"---\nname: {name}\nmetadata:\n") and "description: >-" in text
        assert "## Workflow" in text and "## Rules" in text
        for link in re.findall(r"\]\((references/[\w.-]+)", text):
            assert (ROOT / "skills" / name / link).exists(), link
        named = set(re.findall(r"`([a-z_]+)`", text)) & {t for t in tools} | \
            {t for t in re.findall(r"`([a-z]+_[a-z_]+)`", text) if t.endswith(("_analysis", "_project", "_consumption"))}
        assert named <= tools, named - tools
        assert "estimate_consumption" in named and "prepare_analysis" in named
    plan = (ROOT / "skills" / "competitor-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "get_project" in plan and "breakeven-cpa-check" in plan and "weekly-competitor-report" in plan
    assert "ad-copy-analyst" in (ROOT / "skills" / "competitor-analysis" / "SKILL.md").read_text(encoding="utf-8")
    weekly = (ROOT / "skills" / "weekly-competitor-report" / "SKILL.md").read_text(encoding="utf-8")
    assert "what_changed" in weekly


# --- MCP tools ------------------------------------------------------------------------

def test_levels_over_mcp(tmp_path, monkeypatch):
    studio = Studio(tmp_path)
    monkeypatch.setattr(server, "_client", studio.client)

    async def run():
        async with Client(server.mcp) as client:
            call = lambda name, args=None: client.call_tool(name, args or {})   # noqa: E731
            estimate = (await call("estimate_consumption", {"level": "plan", "ads": 20, "frames": True})).data
            empty = (await call("get_project")).data
            refused = (await call("prepare_analysis", {"country": "IT", "level": "plan", "page_id": PAGE_ID})).data
            bad = (await call("save_project", {**CARD, "product_cost": 400})).data
            saved = (await call("save_project", CARD)).data
            plan = (await call("prepare_analysis", {"country": "IT", "level": "plan", "page_id": PAGE_ID,
                                                    "ads": 2, "frames": True, "language": "it"})).data
            analysis = (await call("prepare_analysis", {"country": "IT", "page_id": PAGE_ID, "ads": 2})).data
            return estimate, empty, refused, bad, saved, plan, analysis

    estimate, empty, refused, bad, saved, plan, analysis = asyncio.run(run())
    assert estimate["ok"] and estimate["band"] in ("medium", "high") and estimate["images"] == 30
    assert empty["project"] is None
    assert refused["outcome"] == "project_required" and "save_project" in refused["note"]
    assert bad["errors"] == {"product_cost": "above_price"}
    assert saved["project"]["market"] == "DE" and saved["numbers"]["cpa"] == 229.0
    assert plan["ok"] and plan["subject"] == "Kingshot" and "text" not in plan
    assert set(plan["files"]) == {"overview", "copy", "creative", "reach", "testing", "project", "brief"}
    assert all(Path(path).exists() for path in plan["files"].values())
    assert len(plan["images"]) == 6 and plan["reach_read"] == 2 and plan["size"]["band"]
    assert "project" not in analysis["files"] and analysis["images"] == []
    assert "Scrivi in italiano." in Path(plan["files"]["brief"]).read_text(encoding="utf-8")
