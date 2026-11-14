import csv
import io
from datetime import date

from ad_library_insights import parser, report, service
from ad_library_insights.client import FetchResult

AS_OF = date(2026, 4, 5)
URL = "https://www.facebook.com/ads/library/?country=DE&q=desk"


def build(cards, advertiser=""):
    fetch = FetchResult(url=URL, outcome="ok", ads=parser.parse_cards(cards),
                        results_label="~300 results", attempts=1, fetched_at=1_775_000_000)
    result = service.assemble(fetch, "standing desk", "DE", advertiser, as_of=AS_OF)
    return result, service.copy_report(result, top_n=5)


def test_assemble_ranks_and_counts(cards):
    result, _ = build(cards)
    assert result["ok"] and result["ads_parsed"] == 3 and result["distinct_ads"] == 2
    assert [row["advertiser"] for row in result["advertisers"]] == ["Northwind Desks", "Caffè Aurora"]
    assert result["advertisers"][0] == {"advertiser": "Northwind Desks", "ads": 2,
                                        "oldest_start": "2026-01-05", "top_score": 60.0}
    assert result["fetched_at"].startswith("2026-")


def test_advertiser_filter_is_case_insensitive(cards):
    result, _ = build(cards, advertiser="aurora")
    assert [ad["advertiser"] for ad in result["ads"]] == ["Caffè Aurora"]
    missing, _ = build(cards, advertiser="nobody")
    assert missing["ads"] == [] and "nobody" in missing["note"]


def test_failed_fetch_carries_a_note():
    blocked = service.assemble(FetchResult(url=URL, outcome="blocked", attempts=3, error="TimeoutError: x"),
                               "q", "DE")
    assert not blocked["ok"] and "retries" in blocked["note"] and "TimeoutError" in blocked["note"]
    empty = service.assemble(FetchResult(url=URL, outcome="no_results", attempts=1), "q", "DE")
    assert "no ads" in empty["note"]


def test_markdown_sections_and_content(cards):
    result, copy = build(cards)
    md = report.to_markdown(result, copy, top_n=5, generated_on=AS_OF)
    assert md.startswith('# Ad Library report: "standing desk" in DE')
    for heading in ("## Top advertisers", "## Top ads", "## Copy patterns in the top 2",
                    "## Copy breakdown", "## Method and limits"):
        assert heading in md
    assert "| 1 | 60.0 | Holding up | low | - | 90 | 1 (dynamic) | Northwind Desks | Still working hunched over a laptop? " \
           "| [1001](https://www.facebook.com/ads/library/?id=1001) |" in md
    assert "The rating (0-100) adds three parts" in md
    assert "- **Hook** (question): Still working hunched over a laptop?" in md
    assert "- Library total for this search: ~300 results" in md
    assert "no spend" in md


def test_markdown_escapes_table_breaking_characters(cards):
    cards[0]["text"] = cards[0]["text"].replace("Northwind Desks", "North | wind")
    cards[0]["links"][0]["text"] = "North | wind"
    result, copy = build(cards[:1])
    assert "North \\| wind" in report.to_markdown(result, copy)


def test_csv_has_one_row_per_ad_with_copy_columns(cards):
    result, _ = build(cards)
    rows = list(csv.DictReader(io.StringIO(report.to_csv(result["ads"]))))
    assert list(rows[0]) == report.CSV_COLUMNS
    assert len(rows) == 2
    first = rows[0]
    assert first["rank"] == "1" and first["library_id"] == "1001"
    assert first["hook_type"] == "question" and first["proof_kinds"] == "reviews;statistic"
    assert first["body"].count("\n") == 3  # multi-line copy survives quoting
    assert first["landing_domain"] == "northwind.example"


def test_write_report_creates_named_files(tmp_path, cards):
    result, copy = build(cards)
    files = report.write_report(result, copy, tmp_path / "out", generated_on=AS_OF)
    assert files["markdown"].endswith("standing-desk-de-2026-04-05.md")
    assert files["csv"].endswith("standing-desk-de-2026-04-05.csv")
    only_csv = report.write_report(result, copy, tmp_path / "csv", formats=("csv",), generated_on=AS_OF)
    assert list(only_csv) == ["csv"]
    assert report.slugify("Caffè in grani / IT") == "caffe-in-grani-it"
