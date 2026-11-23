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
        # three concepts, four ads opened: one concept of three ads is read in part (2 of 3)
        return await service.deepen(studio.client, result, 3, frames=True, ceiling=4)

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
    with pytest.raises(ValueError):
        briefs.test_numbers({**CARD, "product_cost": -10.0})         # a negative cost gave a break-even above the price
    # a goal that cannot be read for sure gives no spend at the level of the goal: the plan asks for it
    unclear = briefs.project_section({**CARD, "goal": "20-30 orders a day"}, "en")
    assert "ask me for it" in unclear and "Goal of" not in unclear


@pytest.mark.parametrize("goal, expected", [
    ("20 ordini al giorno", 20.0), ("140 orders a week", 20.0), ("600 vendite al mese", 20.0),
    ("Arrivare a 12,5 acquisti al giorno", 12.5), ("Farmi conoscere", None), ("", None),
    # second review: these were read as 0.07, 0.05, 0.05, 1.67, 0.33, 600, 600 and 30 orders a day
    ("2 orders a day in 3 months", 2.0), ("1.500 ordini al mese", 50.0), ("1,500 orders a month", 50.0),
    ("50 ordini al giorno entro un mese", 50.0), ("10 ordini al giorno, oggi 2 vendite al mese", None),
    ("al mese 600 vendite", None), ("600 orders a year", None), ("20-30 orders a day", None),
    ("da 20 a 30 ordini al giorno", None), ("30 orders", None), ("100 orders/day", 100.0), ("2.5 sales a day", 2.5),
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
    assert "## On air now, by age" in slices["testing"] and "| 90 days or more |" in slices["testing"]
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
    assert "100 for the one that reaches the most people per day among the ads of 7 days or more" in text
    assert "0 for one that reaches 1,000 times fewer" in text
    assert "never above the weakest ad that was read" in text and "position in Meta's whole list" in text
    assert "(7 at the least, no upper limit)" in text                          # no cap on the days: rating.rate_days
    assert "scaling (14 to 89 days on air, scale of 70 or more and in the top third by people per day)" in text
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


def test_reach_summary_writes_every_figure_with_its_concept(company):
    # it used to pair the best daily figure of one concept with the largest total of another
    from ad_library_insights import signals
    slow = company["ads"][0]                                           # the largest total, made the slowest per day
    slow.update(days_running=600, ad_days=600, newest_days=600)
    for card in slow.get("members") or []:
        card["days"] = 600
    signals.annotate(company["ads"])
    signals.refresh(company["signals"], company["ads"], "IT")
    text = packs.sections(company, ads=3)[0]["reach"]
    fastest = max(company["ads"], key=lambda ad: ad["reach_per_day"])
    assert fastest is not slow and slow["reach_total"] == 1_671_170
    assert f"Most people per day: id {fastest['library_id']}, {fastest['reach_per_day']:,} per day" in text
    assert f"Most people in all: id {slow['library_id']}, 1,671,170 ({slow['reach_per_day']:,} per day" in text
    assert "The two middles can belong to different concepts" in text and "best " not in text


def test_table_by_age_counts_concepts_and_says_so(company):
    text = packs.sections(company, ads=3)[0]["testing"]
    assert "| age of the concept (its oldest ad) | concepts on air |" in text
    assert "counted in concepts (one text with every ad that carries it), not in ads" in text
    assert "| 90 days or more | 3 |" in text and "loaded here: 5" in text      # three concepts, five ads


def test_a_library_count_past_its_limit_is_written_as_a_floor(company):
    company["signals"].update(active_ads=50_001, active_ads_at_least=True)
    slices, _ = packs.sections(company, ads=3)
    assert "5 ads loaded of more than 50,000 active" in slices["overview"]
    assert "Active ads: more than 50,000" in slices["testing"] and "50,001" not in slices["testing"]
    assert "(5 ads of more than 50,000 active)" in briefs.project_section(CARD, "en", company)
    assert "(5 annunci su più di 50.000 attivi)" in briefs.project_section(CARD, "it", company)


def test_keyword_search_does_not_promise_survival_or_a_competitor_pace(company):
    company.pop("mode")                                                # as a keyword search: many advertisers
    text = packs.sections(company, ads=3)[0]["testing"]
    assert "a keyword search loads a sample" in text and "first saved search" not in text
    assert "two searches of one company some days apart, both lists read in full" in text
    numbers = briefs.project_section(CARD, "en", company)
    assert "This was a keyword search" in numbers and "not the pace of one competitor" in numbers
    assert "Pace of" not in numbers


def test_without_reach_the_analysis_brief_does_not_ask_why_the_reach(company):
    from ad_library_insights import signals
    for item in company["ads"]:
        item["reach"] = {**item["reach"], "country_reach": None}
        item.pop("card_reach", None)
    signals.annotate(company["ads"])
    signals.refresh(company["signals"], company["ads"], "IT")
    for lang, asked, table in (("en", "gets the reach shown", "position by impressions, days, creatives"),
                               ("it", "ottiene la copertura che vedi", "posizione per impressioni, giorni, creatività")):
        text = briefs.compose("analysis", company, 3, lang=lang)["text"]
        assert asked not in text and table in text and "NO REACH IN IT" in text
        assert "people reached, per day" not in text and "persone raggiunte, al giorno" not in text
        # the third lens too: nothing is compared by people reached
        assert "People reached and reach per day" not in text and "Persone raggiunte e copertura al giorno" not in text
        assert ("no ad is compared by people reached" in text) == (lang == "en")
    assert "gets the reach shown" in briefs.instructions("analysis", "Northwind", "en")


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
    # an Italian brief writes figures the Italian way: it used to say "fino a 2,862.5"
    assert "Standing desk" in project_file and "572,5" in project_file and "2.862,5" in project_file
    assert "48.090 a settimana" in project_file and "valuta del prezzo" in project_file
    assert "2,862.5" in briefs.project_section(CARD, "en", company) and "currency of the price" in briefs.project_section(CARD, "en")


# --- briefs ---------------------------------------------------------------------------

def test_analysis_brief_works_in_a_single_pass(company):
    made = briefs.compose("analysis", company, 3, frames=True, lang="en")
    text = made["text"]
    assert "You work as a performance marketing specialist on Meta" in text
    assert "social media manager" not in text and "which passes confirm it" in text
    assert "Give every ad a type" in text and "compare only ads of the same age" in text
    assert "An estimate is not a figure." in text
    assert "The reach of a concept is the sum of its ads that were read, up to three" in text
    assert "Do not add reach across concepts" in text and "the reach of one of them" not in text
    assert "do not divide a reach by the age of the concept" in text
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
    # the pace was counted on 5 ads of 194: the plan must not size production on it as if it were the whole account
    assert "The list of Kingshot was read in part (5 ads of 194 active): the real pace is higher" in text
    company["signals"]["ads_loaded"] = 194
    assert "read in part" not in briefs.project_section(CARD, "en", company)
    assert "letto in parte (5 annunci su 194 attivi)" in briefs.project_section(
        CARD, "it", {**company, "signals": {**company["signals"], "ads_loaded": 5}})
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
JURY_AGENT = "ad-skeptical-jury"


def test_each_specialist_agent_reads_only_its_slice():
    folder = ROOT / ".claude" / "agents"
    assert {p.stem for p in folder.glob("*.md")} == set(AGENTS) | {JURY_AGENT}
    for name, data_file in AGENTS.items():
        fields, body = front_matter(folder / f"{name}.md")
        assert fields["name"] == name and len(fields["description"]) > 60
        assert "Read" in fields["tools"]
        assert f"`{data_file}`" in body and "`overview.md`" in body
        others = set(AGENTS.values()) - {data_file}
        assert not [other for other in others if f"`{other}`" in body]
        assert "**Strength**" in body and "Never invent" in body
    assert "start, middle" in (folder / "ad-creative-analyst.md").read_text(encoding="utf-8")

    j_fields, j_body = front_matter(folder / f"{JURY_AGENT}.md")
    assert j_fields["name"] == JURY_AGENT and len(j_fields["description"]) > 60
    assert j_fields["tools"] == "Read, Glob, Grep"
    assert "`overview.md`" in j_body and "`copy.md`" in j_body and "`project.md`" in j_body
    for excluded in ("`creative.md`", "`reach.md`", "`testing.md`"):
        assert excluded not in j_body
    assert "No blocker — ready to test" in j_body
    assert "Never rewrite" in j_body and "Never invent" in j_body


def test_specialists_pin_sonnet_model():
    folder = ROOT / ".claude" / "agents"
    for name in (*AGENTS, JURY_AGENT):
        fields, _ = front_matter(folder / f"{name}.md")
        assert fields.get("model") == "sonnet", (name, fields)


def test_coordinator_enforces_strict_evidence_and_single_neutral_followup():
    analysis = _flat((ROOT / "skills" / "competitor-analysis" / "SKILL.md").read_text(encoding="utf-8"))
    template = _flat((ROOT / "skills" / "competitor-analysis" / "references" / "analysis-template.md").read_text(encoding="utf-8"))
    plan = _flat((ROOT / "skills" / "competitor-plan" / "SKILL.md").read_text(encoding="utf-8"))
    assert "never invent a cause" in analysis.lower()
    assert "at most one neutral follow-up" in analysis.lower()
    assert '"find an error"' in analysis and "four-way debate" in analysis.lower()
    assert "`Out-of-pattern ads (Annunci fuori schema)`" in analysis
    assert "contradict each other" in template and "To test or verify, in order" in template
    assert "at most one neutral follow-up" in plan.lower() and "Risks and what we do not know" in plan
    assert "`check_report`" in analysis and "warning-only" in analysis.lower()
    assert "`check_report`" in plan and "warning-only" in plan.lower()
    assert f"`{JURY_AGENT}`" in plan and "No blocker" in plan


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def pack_texts(company, tmp_path) -> tuple[dict[str, str], set[str]]:
    """Everything the code can write in a pack, per file, over the cases that change the wording.

    Returns the text of each slice (all cases joined) and the names of the files of a plan pack.
    """
    import copy as copies
    from ad_library_insights import signals

    def refresh(result):
        signals.annotate(result["ads"])
        signals.refresh(result["signals"], result["ads"], result["country"])

    cases = [(company, True), (company, False)]
    trap = copies.deepcopy(company)                    # a one-day ad, an ad not delivered in the country, an unread one
    trap["ads"][1].update(days_running=1, ad_days=1, newest_days=1)
    trap["ads"][2]["reach"] = {**trap["ads"][2]["reach"], "country_reach": None}
    refresh(trap)
    cases.append((trap, True))
    marked = copies.deepcopy(company)                  # ended, off topic, flagged, two ages, a video without stills
    marked["ads"][2]["status"] = "inactive"
    refresh(marked)
    marked["ads"][0].update(query_match=False, ad_days=11, needs_review=True)
    marked["signals"]["off_query"] = 1
    marked["ads"][1].pop("frames", None)
    marked["ads"][2]["frames"] = []
    marked["ads"][2]["thumbnail_path"] = None
    marked["changes"] = {"available": True, "previous_taken_at": "2026-11-06T09:00:00+00:00", "days_between": 7.0,
                         "counts": {"new": 4, "new_texts": 2, "stopped": 3, "changed": 0},
                         "survival": {"measurable": True, "groups": [
                             {"age": "under 7 days", "listed_before": 4, "still_listed": 1, "stopped": 3}]}}
    marked["durata"] = {
        "available": True,
        "unit": "concept",
        "window_days": 90,
        "loaded_share": 1.0,
        "concepts_in_window": 14,
        "active_in_window": 7,
        "ended_in_window": 7,
        "excluded_undated": 0,
        "excluded_invalid": 0,
        "outside_window": 0,
        "max_observed_days": 90,
        "tau_days": 90,
        "median_days": 22.0,
        "median_reached": True,
        "rmst_days": 34.5,
        "milestones": {"7": 0.78, "14": 0.64, "30": 0.42, "60": 0.3, "90": 0.2},
        "weibull": {"shape_k": 0.78, "scale_days": 28.4, "regime": "early_cut"},
        "lindy": [{"after_days": 30, "horizon_days": 30, "at_risk": 6, "still_active_share": 0.71}],
        "longest_active": [{"library_id": "101", "days": 85}],
        "fastest_ended": [{"library_id": "202", "days": 3}],
    }
    marked["ritmo"] = {
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
            "recent_ids": ["101", "102"],
            "survivor_bias_caveat": False,
            "trigger_ai": True,
            "weeks": [],
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
            "example_ids": ["101", "102"],
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
    }
    marked["struttura"] = {
        "available": True,
        "mode": "company",
        "sample_scope": "company",
        "country": "IT",
        "concepts_total": 10,
        "reach_concentration": {
            "measurable": True,
            "scope": "market",
            "country": "IT",
            "concepts_with_reach": 5,
            "total_read_reach": 100000,
            "top1_share": 0.60,
            "top3_share": 0.90,
            "top20pct_share": 0.60,
            "hhi": 0.41,
            "normalized_hhi": 0.26,
            "effective_n": 2.4,
            "gini": 0.52,
            "level": "concentrated",
            "leaders": [{"library_id": "101", "share": 0.60, "reach": 60000, "cards_read": 1, "cards": 1}],
        },
        "copy_families": {
            "measurable": True,
            "evaluated": 8,
            "total_with_text": 8,
            "capped": False,
            "threshold": 0.62,
            "families_count": 3,
            "diversity_ratio": 0.38,
            "largest_family_share": 0.50,
            "median_pairwise_ncd": 0.71,
            "top_families": [{"representative_id": "101", "size": 4, "share": 0.50, "opening": "Sample opening", "member_ids": ["101"]}],
        },
        "shannon": {
            "formats": {"measurable": True, "items": 8, "categories": 2, "entropy_bits": 0.81, "effective_k": 1.75, "evenness": 0.81, "dominant": "video", "dominant_share": 0.75, "label": "balanced"},
            "destinations": {"measurable": True, "items": 8, "categories": 2, "entropy_bits": 0.81, "effective_k": 1.75, "evenness": 0.81, "dominant": "example.com", "dominant_share": 0.75, "label": "balanced"},
        },
        "audience_drift": {
            "measurable": True,
            "js_distance": 0.21,
            "js_divergence": 0.044,
            "state": "drifting",
            "top_gainers": [{"country": "IT", "age_range": "25-34", "gender": "female", "delta": 0.08}],
            "top_losers": [],
            "days_between": 14.0,
            "snapshots_with_audience": 2,
        },
    }
    marked["anomalie"] = {
        "available": True,
        "mode": "company",
        "sample_scope": "company",
        "concepts_checked": 10,
        "active_checked": 9,
        "status": "flagged",
        "baselines": {"median_days": 30.0, "median_reach_per_day": 500.0, "median_body_chars": 150.0, "reach_peers": 6},
        "items": [{
            "library_id": "101",
            "kind": "long_live_low_reach",
            "kinds": ["long_live_low_reach"],
            "lenses": ["reach", "copy"],
            "strength": 4.2,
            "opening": "Quiet steady offer",
            "detail": "90d on air vs 30d median, yet only 80/day vs 500/day median",
        }],
    }
    cases.append((marked, True))
    unread = copies.deepcopy(company)                  # reach not read at all, then not published in the country
    for ad in unread["ads"]:
        ad.pop("reach", None)
        ad.pop("card_reach", None)
    refresh(unread)
    cases.append((unread, False))
    nowhere = copies.deepcopy(company)
    for ad in nowhere["ads"]:
        ad["reach"] = {**ad["reach"], "country_reach": None}
        ad.pop("card_reach", None)
    refresh(nowhere)
    cases.append((nowhere, False))

    texts = {key: "" for key in packs.SLICES}
    for result, frames in cases:
        for key, text in packs.sections(result, ads=3, frames=frames)[0].items():
            texts[key] += _flat(text) + " "
    made = briefs.prepare("plan", company, 3, True, CARD, "en", tmp_path / "packs", TODAY)
    texts["project"] = _flat(Path(made["files"]["project"]).read_text(encoding="utf-8"))
    files = {p.name for p in Path(made["folder"]).iterdir()}
    return texts, files


def _quoted(text: str) -> set[str]:
    """What a file puts between backticks, outside its fenced examples."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return {_flat(token) for token in re.findall(r"`([^`]+)`", text) if "{" not in token}


def test_specialists_quote_only_what_the_pack_writes(company, tmp_path):
    # a specialist told to look for a line the pack never writes will invent it or miss the real one
    texts, files = pack_texts(company, tmp_path)
    for name, data_file in AGENTS.items():
        body = (ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
        own = texts["overview"] + texts[data_file[:-3]]
        for token in _quoted(body):
            if token in files:
                assert token in ("overview.md", data_file, packs.FRAMES_FOLDER), (name, token)
            else:
                assert token in own, (name, token)
        for stale in ("one ad of the group", "local paths", "single use of the text", "thumbnail"):
            assert stale not in body, (name, stale)
    for name in ("ad-copy-analyst", "ad-creative-analyst"):
        body = (ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
        assert "**Types**" in body and "Ad types" in body and "## Ad types" in texts["overview"]
    reach = _flat((ROOT / ".claude" / "agents" / "ad-reach-analyst.md").read_text(encoding="utf-8"))
    assert "Localisation" in reach and "added up" in reach and "seven at the least" in reach
    testing = _flat((ROOT / ".claude" / "agents" / "ad-testing-analyst.md").read_text(encoding="utf-8"))
    assert "State a survival or cut rate only from that table" in testing


def test_level_skills_quote_only_what_the_code_makes(company, tmp_path):
    texts, files = pack_texts(company, tmp_path)
    everything = " ".join(texts.values())
    tools = tool_names()
    skills = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    for name in ("competitor-analysis", "competitor-plan"):
        folder = ROOT / "skills" / name
        for path in (folder / "SKILL.md", *sorted((folder / "references").glob("*.md"))):
            for token in _quoted(path.read_text(encoding="utf-8")):
                known = (token in files or token in AGENTS or token == JURY_AGENT or token in skills
                         or token in tools or token in briefs.LEVELS or token in everything)
                assert known, (path.name, token)
    plan = _flat((ROOT / "skills" / "competitor-plan" / "SKILL.md").read_text(encoding="utf-8"))
    for step in ("Check before spending", "campaign structure", "creative pace", "Conversions API", "Use them as they are"):
        assert step in plan, step
    template = (ROOT / "skills" / "competitor-plan" / "references" / "plan-template.md").read_text(encoding="utf-8")
    assert "copy used" not in template and "EU and UK ads read" not in template
    analysis = _flat((ROOT / "skills" / "competitor-analysis" / "SKILL.md").read_text(encoding="utf-8"))
    assert "which lenses confirm it" in analysis and "Give every ad one type" in analysis


def test_skills_and_specialists_carry_no_example_of_a_sector():
    # keyword, company and country are parameters: names from the saved searches stay in tests, docs and examples
    names = {"kingshot", "zalando", "hoka", "decathlon", "flexora", "cappelletto", "gabrieli", "standing desk",
             "scarpe", "fitness", "padel"}
    for path in [*(ROOT / "skills").rglob("*.md"), *(ROOT / ".claude" / "agents").glob("*.md")]:
        text = path.read_text(encoding="utf-8").casefold()
        assert not [word for word in names if word in text], path


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


@pytest.mark.parametrize("goal", [
    "between 20 and 30 orders a day", "tra 20 e 30 ordini al giorno", "20/30 ordini al giorno",
    "300 ordini in 30 giorni", "500 orders in 90 days", "30 ordini ogni 2 giorni", "10 orders every 2 days",
    "50 orders in 2 months", "100 orders by Friday", "15 sales per weekend", "60 orders bi-weekly",
    "40 orders every other day",
])
def test_a_goal_with_a_range_or_an_odd_period_is_asked_not_guessed(goal):
    assert briefs.orders_per_day(goal) is None


@pytest.mark.parametrize("goal, a_day", [
    ("20 ordini al giorno", 20), ("20 ordini/giorno", 20), ("20 orders a day", 20), ("20 orders per day", 20),
    ("20 orders daily", 20), ("140 ordini a settimana", 20), ("140 ordini alla settimana", 20),
    ("140 orders/week", 20), ("140 orders weekly", 20), ("1.500 ordini al mese", 50), ("1,500 orders a month", 50),
    ("600 ordini mensili", 20), ("600 vendite ogni mese", 20), ("600 sales each month", 20),
])
def test_a_plain_goal_is_still_read(goal, a_day):
    assert briefs.orders_per_day(goal) == a_day


def test_reach_read_on_an_ad_without_a_start_date_is_written_not_hidden():
    undated = {"library_id": "1", "reach_total": 100_000, "reach_in_market": True, "reach_cards_read": 1, "cards": 1}
    line = packs._reached(undated, "IT")
    assert "100,000 people reached in IT" in line and "per day not known" in line and "not known;" not in line
    # one ad with a date and one without: the total covers two ads, the rate only one, and the line says so
    mixed = {"library_id": "2", "reach_total": 901_000, "reach_per_day": 10, "reach_in_market": True,
             "reach_cards_read": 2, "reach_cards_dated": 1, "cards": 2}
    assert "2 of 2 ads read; per day counted on the 1 with a start date" in packs._reached(mixed, "IT")
    whole = {**mixed, "reach_cards_dated": 2}
    assert "start date" not in packs._reached(whole, "IT")


@pytest.mark.parametrize("goal", [
    # third review: each of these was read as a figure of orders a day that the phrase does not mean
    "1 500 ordini al mese", "1'500 orders a month", "dai 20 ai 30 ordini al giorno",
    "tra i 20 e i 30 ordini al giorno", "between 20 & 30 orders a day", "20 ~ 30 ordini al giorno",
    "minimo 20 massimo 30 ordini al giorno", "20 fino a 30 ordini al giorno", "20, max 30 orders a day",
    "almeno 20, idealmente 30 ordini al giorno", "da 10 ordini al giorno a 30", "go from 5 orders a day to 20",
    "oggi facciamo 5 ordini al giorno, vogliamo arrivare a 20", "5 ordini al giorno oggi, obiettivo 20 al giorno",
    "aumentare di 20 ordini al giorno", "+20 orders a day", "altri 20 ordini al giorno",
    "raddoppiare i 20 ordini al giorno", "double our 20 orders a day", "triple the current 10 sales a day",
    "20 ordini al giorno lavorativo", "30 ordini al giorno nei giorni feriali", "10 orders a day on weekends",
    "20 ordini al giorno nel weekend", "5 ordini al giorno per 4 negozi", "20 orders a day per 10 stores",
    "20 sales a day of 3 products each", "0,500 ordini al giorno", "ridurre a 20 ordini al giorno i resi",
])
def test_a_goal_that_is_not_one_plain_total_is_asked(goal):
    assert briefs.orders_per_day(goal) is None


@pytest.mark.parametrize("goal, a_day", [
    ("20 ordini al gg", 20), ("20 ordini/gg", 20), ("140 ordini la settimana", 20), ("20 ordini il giorno", 20),
    ("ROAS 3 e 20 ordini al giorno", 20), ("20 ordini al giorno con ROAS 3", 20),
    ("20 ordini al giorno entro il 2027", 20), ("20 orders a day within 3 months", 20),
    ("almeno 20 ordini al giorno", 20), ("Arrivare a circa 20 ordini al giorno, senza alzare i prezzi", 20),
    ("20 ordini al giorno spendendo meno di 500 €", None),
])
def test_other_figures_pass_only_when_they_are_plainly_something_else(goal, a_day):
    assert briefs.orders_per_day(goal) == a_day


def test_the_pack_holds_the_concepts_that_were_read_not_the_ones_that_rose_above_them():
    # after reach is read the list is rated again: on a saved search 4 of the "top 10" had never been opened
    def concept(name, score, read):
        made = {"library_id": name, "score": score}
        if read:
            made["reach"] = {"available": True}
        return made
    result = {"ads": [concept("unread-high", 90, False), concept("a", 80, True), concept("b", 70, True),
                      concept("unread-low", 10, False)]}
    assert [ad["library_id"] for ad in packs.chosen(result, 2)] == ["a", "b"]
    assert [ad["library_id"] for ad in packs.chosen(result, 3)] == ["a", "b", "unread-high"]
    assert "the 2 concepts whose ads were opened" in packs._contents(packs.chosen(result, 2))
    assert "the 2 whose ads were opened" in packs._contents(packs.chosen(result, 3))
    assert "then 1 that were not opened" in packs._contents(packs.chosen(result, 3))
    nothing = {"ads": [concept("x", 5, False), concept("y", 4, False)]}
    assert [ad["library_id"] for ad in packs.chosen(nothing, 1)] == ["x"]
    assert "none of them was opened" in packs._contents(packs.chosen(nothing, 1))
    # a concept read only through its second ad counts as read
    assert packs.was_read({"library_id": "z", "card_reach": {"z2": {"available": True}}})


def test_mcp_save_project_preserves_optional_costs_and_single_pass_mentions_new_sections(tmp_path, monkeypatch):
    from ad_library_insights import project as project_mod

    studio = Studio(tmp_path)
    monkeypatch.setattr(server, "_client", studio.client)

    # First save optional real costs (as the web UI does), then update goal via MCP without passing them
    project_mod.save({**CARD, "market": "IT", "vat_pct": 22.0, "shipping_cost": 5.0})

    async def run():
        async with Client(server.mcp) as client:
            res = (await client.call_tool("save_project", {
                "product": CARD["product"], "price": 122.0, "product_cost": 35.0,
                "market": "IT", "goal": "10 orders a day", "main_problem": CARD["main_problem"],
            })).data
            prep = (await client.call_tool("prepare_analysis", {
                "country": "IT", "level": "analysis", "page_id": PAGE_ID, "ads": 2, "active_status": "all",
            })).data
            return res, prep

    res, prep = asyncio.run(run())
    assert res["ok"] is True
    assert res["project"]["vat_pct"] == 22.0 and res["project"]["shipping_cost"] == 5.0
    assert res["numbers"]["cpa"] < 122.0 - 35.0
    assert prep["ok"] is True

    for lang in ("en", "it"):
        txt = briefs.instructions("analysis", "Northwind", lang)
        assert "Copy families (Su cosa si regge)" in txt
        assert "Out-of-pattern ads (Annunci fuori schema)" in txt
        assert "Account structure (Su cosa si regge)" in txt
        assert "Duration and survival (cohort)" in txt
        assert "Pace and format drift (Ritmo)" in txt
