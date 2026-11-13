"""Reading ads from the page's own data. Fixtures are responses saved from real pages."""
import json
from pathlib import Path

from ad_library_insights import parser, records

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def keyword_ads():
    return records.ads_from_edges(records.connection_from_text(load("search_results_keyword.json"))["edges"])


def test_connection_is_found_in_a_response_and_in_a_streamed_body():
    text = load("search_results_keyword.json")
    assert records.connection_from_text(text)["count"] == 327
    streamed = text + '\n{"label":"later chunk"}'
    assert len(records.connection_from_text(streamed)["edges"]) == 5
    assert records.connection_from_text('{"data": {}}') is None
    assert records.connection_from_text("not json search_results_connection") is None


def test_ads_keep_page_order_as_impression_rank():
    ads = keyword_ads()
    assert [ad["impression_rank"] for ad in ads] == [1, 2, 3, 4, 5]
    assert [ad["advertiser"] for ad in ads][:2] == ["Subito", "Zalando"]


def test_structured_ad_has_the_fields_the_card_parser_gives(card):
    from_card = parser.parse_card(card)
    ad = keyword_ads()[3]
    assert set(from_card) <= set(ad)
    assert ad["library_id"] == "1648829336414617"
    assert ad["ad_url"].endswith("?id=1648829336414617")
    assert (ad["status"], ad["started"], ad["ended"]) == ("active", "2026-06-09", None)
    assert (ad["media_type"], ad["cta"], ad["landing_domain"]) == ("image", "Shop now", "valsportrunning.com")
    assert ad["image_url"].startswith("https://")
    assert len(ad["platforms"]) == 5 and "instagram" in ad["platforms"]
    assert ad["page_id"] and ad["logo_url"].startswith("https://")


def test_a_group_of_ads_is_one_card_with_its_counter():
    grouped = keyword_ads()[1]
    assert grouped["copies"] == 2
    assert grouped["collation_ids"] == ["1826881371684190"]
    assert "1826881371684190" not in {ad["library_id"] for ad in keyword_ads()}


def test_placeholders_of_dynamic_ads_are_replaced_by_the_first_variation():
    catalogue = keyword_ads()[0]
    assert catalogue["format"] == "dpa" and catalogue["multiple_versions"]
    assert "{{" not in (catalogue["headline"] or "")
    assert catalogue["headline"]


def test_video_ads_carry_thumbnail_and_video_address():
    video = keyword_ads()[4]
    assert video["media_type"] == "video"
    assert video["video_url"].startswith("https://") and video["image_url"].startswith("https://")


def test_repeated_edges_are_dropped():
    edges = records.connection_from_text(load("search_results_page.json"))["edges"]
    assert len(records.ads_from_edges(edges + edges)) == 5


def test_typeahead_lists_pages_with_followers_and_category():
    pages = records.pages_from_typeahead(json.loads(load("typeahead_pages.json")))
    assert len(pages) == 15
    first = pages[0]
    assert (first["name"], first["page_id"], first["followers"]) == ("Zalando", "365604620536", 8941792)
    assert first["category"] == "Shopping & Retail" and first["verified"]
    assert records.pages_from_typeahead({"data": {}}) == []
