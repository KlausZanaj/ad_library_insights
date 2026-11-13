from ad_library_insights import parser

from conftest import make_card


def test_core_fields(card):
    ad = parser.parse_card(card)
    assert ad["library_id"] == "1001"
    assert ad["ad_url"] == "https://www.facebook.com/ads/library/?id=1001"
    assert ad["status"] == "active"
    assert ad["started"] == "2026-01-05"
    assert ad["ended"] is None
    assert ad["copies"] == 1
    assert ad["multiple_versions"] is True
    assert ad["advertiser"] == "Northwind Desks"
    assert ad["advertiser_url"] == "https://www.facebook.com/northwinddesks/"


def test_body_is_separated_from_link_preview(card):
    ad = parser.parse_card(card)
    assert ad["body"].splitlines() == [
        "Still working hunched over a laptop?", "Raise your desk in 3 seconds.",
        "Rated 4.8/5 by 12,000 customers.", "\U0001F449 Order today with free shipping"]
    assert ad["headline"] == "Sit-stand desk, oak top"
    assert ad["description"] == "Free 30-day returns"
    assert ad["cta"] == "Shop Now"


def test_landing_url_is_unwrapped(card):
    ad = parser.parse_card(card)
    assert ad["landing_url"] == "https://www.northwind.example/desk?utm_source=fb"
    assert ad["landing_domain"] == "northwind.example"


def test_copies_counter_summary_variant_and_video(cards):
    ad = parser.parse_card(cards[1])
    assert ad["copies"] == 2
    assert ad["advertiser"] == "Caffè Aurora"
    assert ad["media_type"] == "video"
    assert ad["image_url"] == "https://scontent.example/poster.jpg"
    assert "0:00" not in ad["body"]
    assert ad["headline"] == "Miscela Aurora 1 kg"
    assert ad["description"] is None
    assert ad["cta"] == "Learn more"


def test_inactive_ad_date_range():
    ad = parser.parse_card(make_card(status="Inactive", started="Jan 5, 2026 - Feb 4, 2026"))
    assert (ad["status"], ad["started"], ad["ended"]) == ("inactive", "2026-01-05", "2026-02-04")


def test_card_without_link_preview():
    ad = parser.parse_card(make_card(preview=None))
    assert ad["cta"] is None and ad["landing_url"] is None and ad["headline"] is None
    assert ad["body"].startswith("Still working")


def test_inline_body_link_is_not_the_preview(card):
    card["links"].insert(1, {"href": "https://l.facebook.com/l.php?u=https%3A%2F%2Fother.example",
                             "text": "www.other.example"})
    assert parser.parse_card(card)["landing_domain"] == "northwind.example"


def test_non_ad_card_is_skipped_and_duplicates_dropped(cards):
    ads = parser.parse_cards([{"text": "Filters\nSort", "links": []}, *cards, cards[0]])
    assert [ad["library_id"] for ad in ads] == ["1001", "1002", "1003"]


def test_results_label_and_no_results():
    assert parser.results_label("Cookies\n~300 results\nThese results include") == "~300 results"
    assert parser.results_label("1,200 results") == "1,200 results"
    assert parser.results_label("Log in") is None
    assert parser.says_no_results("0 results\nNo ads match your search")
    assert not parser.says_no_results("~300 results")
    assert not parser.says_no_results("10 results")
