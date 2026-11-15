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
        return await service.deepen(studio.client, result, 4, frames=True)      # four ads cover the three concepts

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
                       "per_ad": 572.5, "round_total": 2862.5, "multiplier": 2.5, "ideas": 5,
                       # "30 orders a day": spend at break-even, a fifth of it for tests, ads it can test
                       "orders": 30.0, "daily_max": 6870.0, "weekly_max": 48090.0, "share": 20,
                       "weekly_test": 9618.0, "capacity": 16}
    assert briefs.test_numbers(CARD, pace=4.5)["pace"] == 4.5
    assert "orders" not in briefs.test_numbers({**CARD, "goal": "Grow the brand"})
    with pytest.raises(ValueError):
        briefs.test_numbers({**CARD, "product_cost": 349.0})


@pytest.mark.parametrize("goal, expected", [
    ("20 ordini al giorno", 20.0), ("140 orders a week", 20.0), ("600 vendite al mese", 20.0),
    ("Arrivare a 12,5 acquisti al giorno", 12.5), ("Farmi conoscere", None), ("", None),
])
def test_orders_per_day_are_read_from_the_goal(goal, expected):
    assert briefs.orders_per_day(goal) == expected


# --- data pack ------------------------------------------------------------------------

def test_slices_cover_the_four_lenses(company):
    slices, pictures = packs.sections(company, ads=3, frames=True)
    assert tuple(slices) == packs.SLICES
    assert "## Ad types" in slices["overview"] and "UGC or creator" in slices["overview"]
    assert "type hint from the format: video" in slices["copy"] and "type hint from the format" in slices["creative"]
    assert "## Languages and countries" in slices["reach"] and "Where delivery goes" in slices["reach"]
    assert "## Ads on air now, by age" in slices["testing"] and "| 90 days or more |" in slices["testing"]
    assert "Survival: NOT MEASURABLE" in slices["testing"] and "first saved search" in slices["testing"]
    assert "three parts that always weigh the same: scale" in slices["overview"]
    assert "Reliability of a rating" in slices["overview"]
    assert "do not count as creatives" in slices["overview"]
    assert "Meta publishes no spend and no sales" in slices["overview"]
    top = company["ads"][0]
    assert f"id {top['library_id']}" in slices["copy"] and "> " in slices["copy"]
    assert "first pass made by rules" in slices["copy"]
    assert "| 835,585 (1 of 1 ads read) |" in slices["reach"] and "| 7,398,228 | 1,679,270 |" in slices["reach"]
    assert "| 1,671,170 (2 of 3 ads read) |" in slices["reach"]             # two ads of one concept, added up
    assert "Locations targeted (ads):" in slices["reach"] and "Italy" in slices["reach"]
    assert "Launches per week" in slices["testing"] and "itunes.apple.com" in slices["testing"]
    assert len(pictures) == 9 and all(Path(p["source"]).exists() for p in pictures)   # three stills for three videos
    assert pictures[0]["name"].startswith("frames/01-") and pictures[0]["name"].endswith("-start.jpg")
    assert "frames/01-" in slices["creative"] and str(Path(pictures[0]["source"]).parent) not in slices["creative"]


def test_overview_describes_the_rating_the_code_computes(company):
    # the specialists judge every ad from these lines: they must say what rating.py does, not an older version
    text = packs.sections(company, ads=3)[0]["overview"]
    assert "scale, up to 60 points" in text and "staying power, up to 25" in text and "creative investment, up to 15" in text
    assert "full at 90" in text and "full at 10" in text                       # fixed thresholds
    assert "100 for the one that reaches the most people per day, 0 for one that reaches 1,000 times fewer" in text
    assert "(7 at the least, no upper limit)" in text                          # no cap on the days: rating.rate_days
    assert "scaling (14 to 89 days on air and in the top third by people per day)" in text
    assert "ended (no longer on air)" in text and "not a negative verdict" in text
    assert "only when at least 5 concepts were read" in text
    assert "up to 3 of its ads are read" in text and "Reach is never added across concepts" in text
    assert "that of one ad of the group" not in text and "relative to the other ads here" not in text
    assert "off topic" not in text and "words searched" not in text            # a company search has no keyword


def test_a_concept_shows_its_age_and_the_age_of_its_most_shown_ad(company):
    # reach per day comes from the ads read, staying power from the oldest ad: one age alone would mislead
    top = company["ads"][0]
    top["ad_days"] = 11
    slices, _ = packs.sections(company, ads=3)
    assert "120 (most shown ad: 11) days" in slices["copy"]
    assert f"| 1 | {top['library_id']} | 120 (most shown ad: 11) |" in slices["reach"]
    assert "| 120 (most shown ad: 11) | 2 | video |" in slices["testing"]
    assert "people reached in IT, 14,629 per day (2 of 3 ads read)" in slices["copy"]
    assert "## Across the 3 concepts with reach in IT" in slices["reach"]
    assert "Concepts are not added to each other" in slices["reach"]


def test_launch_pace_says_how_much_of_the_list_it_was_counted_on(company):
    text = packs.sections(company, ads=3)[0]["testing"]
    assert "Counted on the 5 ads loaded, of 194 active: the list was read in part" in text
    assert "the real launch pace is higher than this figure" in text
    company["signals"]["ads_loaded"] = company["signals"]["active_ads"]
    assert "the list was read in full" in packs.sections(company, ads=3)[0]["testing"]


def test_ended_and_off_topic_ads_are_marked_in_the_pack(company):
    from ad_library_insights import signals
    last = company["ads"][-1]
    last["status"] = "inactive"
    signals.annotate(company["ads"])
    company["ads"][0]["query_match"] = False
    company["signals"]["off_query"] = 1
    slices, _ = packs.sections(company, ads=3)
    assert "ended, reliability" in slices["copy"] and "no longer on air" in slices["copy"]
    assert f"{last['library_id']} (no longer on air)" in slices["reach"]
    assert "| 90 days or more | 2 |" in slices["testing"]                      # the ended one is not "on air now"
    assert "Concepts no longer on air, left out of the table: 1" in slices["testing"]
    assert "the words searched are not in its visible text" in slices["copy"]
    assert "1 of the 3 concepts loaded do not show the words searched" in slices["overview"]


def test_trap_pack_one_day_ad_foreign_only_ad_and_market_without_reach(company):
    """Three cases that have already produced wrong statements, in one pack.

    An ad of one day, an ad delivered only outside the country searched, and then a
    market with no published reach at all. The files must say "too recent to judge",
    "not published" and "NO REACH IN", and must not carry a figure that invites the
    opposite reading.
    """
    from ad_library_insights import signals
    first, young, abroad = company["ads"]
    young.update(days_running=1, ad_days=1, newest_days=1)
    young["reach"] = {**young["reach"], "country_reach": 476}               # as the real one-day ad: 476 people in Italy
    abroad["reach"] = {**abroad["reach"], "country_reach": None}            # delivered in the EU, not in Italy
    signals.annotate(company["ads"])
    signals.refresh(company["signals"], company["ads"], "IT")
    by_id = {ad["library_id"]: ad for ad in company["ads"]}
    assert by_id[young["library_id"]]["verdict"] == "testing" and by_id[abroad["library_id"]]["reliability"] != "high"
    made = briefs.compose("analysis", company, 3, lang="en")
    slices, text = made["slices"], made["text"]

    young_line = next(line for line in slices["copy"].splitlines() if line.startswith("rating") and " 1 days" in line)
    assert "too recent to judge" in young_line and "scaling" not in young_line
    assert f"{young['library_id']} (too recent to judge)" in slices["reach"]
    assert "An ad on air for less than 7 days is too recent to judge" in text

    assert "reach in IT: not published (the reach read is for the EU or the UK and does not count here)" in slices["copy"]
    abroad_row = next(line for line in slices["reach"].splitlines() if f"| {abroad['library_id']}" in line)
    assert "| not published | n/a | 7,398,228 |" in abroad_row              # the EU total stays, as information
    assert "NO REACH IN" not in slices["overview"]                           # one concept still has reach in Italy
    assert "Reach in IT: read for 2 of these 3 concepts" in slices["overview"]

    for ad in company["ads"]:
        ad["reach"] = {**ad["reach"], "country_reach": None}
        ad.pop("card_reach", None)
    signals.annotate(company["ads"])
    signals.refresh(company["signals"], company["ads"], "IT")
    made = briefs.compose("analysis", company, 3, lang="en")
    assert "NO REACH IN IT" in made["slices"]["overview"] and "NO REACH IN IT" in made["text"]
    assert "people reached in IT" not in made["slices"]["copy"]
    assert "## Reach in IT: not published" in made["slices"]["reach"]
    assert not [ad for ad in company["ads"] if ad["verdict"] in ("scaling", "review")]


def test_survival_table_is_shown_when_two_full_searches_exist(company):
    company["changes"] = {"available": True, "previous_taken_at": "2026-11-06T09:00:00+00:00", "days_between": 7.0,
                          "counts": {"new": 4, "new_texts": 2, "stopped": 3, "changed": 0},
                          "survival": {"measurable": True, "groups": [
                              {"age": "under 7 days", "listed_before": 4, "still_listed": 1, "stopped": 3},
                              {"age": "90 days or more", "listed_before": 5, "still_listed": 5, "stopped": 0}]}}
    text = packs.sections(company, ads=3)[0]["testing"]
    assert "| under 7 days | 4 | 1 | 3 | 25% |" in text and "| 90 days or more | 5 | 5 | 0 | 100% |" in text
    assert "NOT MEASURABLE" not in text and "Compare each group only with itself" in text
    company["changes"]["survival"] = {"measurable": False, "reason": "sample"}
    assert "a keyword search loads a sample" in packs.sections(company, ads=3)[0]["testing"]


def test_without_reach_in_the_country_the_pack_says_so(company):
    for item in company["ads"]:
        if item.get("reach", {}).get("available"):
            item["reach"] = {**item["reach"], "country": "US", "country_reach": None}
        item.pop("card_reach", None)
    from ad_library_insights import signals
    signals.annotate(company["ads"])
    signals.refresh(company["signals"], company["ads"], "US")
    company["country"] = "US"
    slices, _ = packs.sections(company, ads=3)
    assert "NO REACH IN US" in slices["overview"] and "as if they were known" in slices["overview"]
    assert "people reached in US" not in slices["copy"] and "reach in US: not published" in slices["copy"]
    assert "## Reach in US: not published" in slices["reach"] and "| not published |" in slices["reach"]


def test_reach_table_says_which_ads_were_not_read(company):
    company["ads"][-1].pop("reach")                    # as for an ad below the ones opened
    company["ads"][-2]["reach"] = {"available": False}
    slices, _ = packs.sections(company, ads=5)
    assert slices["reach"].count("| not read |") == 1 and slices["reach"].count("| not published |") == 1


def test_without_stills_the_creative_slice_says_so(company):
    slices, pictures = packs.sections(company, ads=3, frames=False)
    assert "Pictures: not collected for this pack" in slices["creative"]
    assert "picture:" not in slices["creative"] and "stills (start" not in slices["creative"]
    assert pictures == []


def test_pack_is_written_one_file_per_specialist(company, tmp_path):
    made = briefs.prepare("analysis", company, 3, True, lang="en", directory=tmp_path / "packs", today=TODAY)
    folder = Path(made["folder"])
    assert folder.name == "kingshot-it-analysis-2026-11-13"
    assert sorted(p.name for p in folder.iterdir()) == ["brief.md", "copy.md", "creative.md", "frames", "manifest.json",
                                                         "overview.md", "reach.md", "testing.md"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "analysis" and manifest["ads"] == 3 and len(manifest["images"]) == 9
    # the pictures of this analysis, and only those, sit in the pack; no text names a folder of the computer
    assert made["frames_folder"] == str(folder / "frames") and len(list((folder / "frames").iterdir())) == 9
    assert all(Path(path).parent == folder / "frames" for path in made["images"])
    for name in ("brief.md", "creative.md", "manifest.json"):
        assert str(tmp_path) not in (folder / name).read_text(encoding="utf-8")
    assert (folder / "brief.md").read_text(encoding="utf-8") == made["text"]
    assert "slices" not in made and made["ads"] == 3 and made["frames"] is True
    (folder / "frames" / "left-over.jpg").write_bytes(b"old")
    again = briefs.prepare("analysis", company, 1, True, lang="en", directory=tmp_path / "packs", today=TODAY)
    assert len(list((folder / "frames").iterdir())) == 3 == len(again["images"])


def test_plan_pack_adds_the_project_file(company, tmp_path):
    made = briefs.prepare("plan", company, 3, False, CARD, "it", tmp_path / "packs", TODAY)
    project_file = Path(made["files"]["project"]).read_text(encoding="utf-8")
    assert "Standing desk" in project_file and "572.5" in project_file and "2,862.5" in project_file


# --- briefs ---------------------------------------------------------------------------

def test_analysis_brief_works_in_a_single_pass(company):
    made = briefs.compose("analysis", company, 3, frames=True, lang="en")
    text = made["text"]
    assert "You work as a performance marketing specialist on Meta" in text
    assert "social media manager" not in text and "which passes confirm it" in text
    assert "Give every ad a type" in text and "compare only ads of the same age" in text
    assert "An estimate is not a figure." in text
    for heading in ("### Copy", "### Creative", "### Reach and audience", "### Testing and destinations"):
        assert heading in text
    assert text.count("\n1. ") >= 2 and "finding · evidence" in text
    assert "What this data cannot tell." in text and "Write in English." in text
    assert "## Pictures to attach" in text and len(made["images"]) == 9
    assert "Attach the 9 pictures of the folder \"frames\"" in text and "\n- 01-" in text
    assert made["size"]["tokens"] > made["size"]["tokens_single_pass"]        # re-reads are counted


def test_brief_without_stills_tells_the_assistant(company):
    made = briefs.compose("analysis", company, 3, frames=False, lang="it")
    assert made["images"] == []
    assert "nessuna: scrivi che la lettura delle creatività si basa solo su formati e testi" in made["text"]
    assert "Scrivi in italiano." in made["text"]


def test_plan_brief_starts_from_the_project(company):
    text = briefs.compose("plan", company, 3, project=CARD, lang="en")["text"]
    assert "You work as head of marketing for a business that sells online." in text
    assert "social media manager" not in text
    assert "Check before spending." in text and "Conversions" in text and "purchase event arrives with value" in text
    assert "Campaign structure." in text and "Broad or narrow audience" in text
    assert "how many new\ncreatives" not in text and "how many new creatives a week I have to produce" in text
    assert 'write "You" in the Who column' in text
    assert "Goal of 30 orders a day: at break-even the most to spend is 6,870 a day (30 × 229), 48,090 a week" in text
    assert "9,618 a week, enough for 16 new ads a week at 572.5 each" in text
    assert "Pace of Kingshot:" in text and "VAT, shipping, payment fees and returns are not included" in text
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
        assert plan.count("\n7. ") == 1 and "Northwind" in plan              # seven steps
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
