import pytest

from ad_library_insights import copy_analysis, parser


@pytest.mark.parametrize("text,expected", [
    ("Still working hunched over a laptop?", "question"),
    ("¿Cansado de esperar?", "question"),
    ("-30% on every order this week", "offer"),
    ("Spedizione gratuita su tutto", "offer"),
    ("Tired of cables everywhere", "pain_point"),
    ("Stanco del solito caffè", "statement"),       # "stanco del" is not a listed phrase
    ("Stanco di aspettare", "pain_point"),
    ("Loved by 12,000 customers", "social_proof"),
    ("3 reasons to switch", "number"),
    ("\U0001F525 Discover the new collection", "command"),
    ("Scopri la miscela tostata a mano", "command"),
    ("The quiet upgrade for your home office", "statement"),
])
def test_hook_type(text, expected):
    assert copy_analysis.hook_type(text) == expected


def test_segments_split_lines_then_sentences():
    assert copy_analysis.split_segments("One. Two!\n\nThree?  Four\n") == ["One.", "Two!", "Three?", "Four"]


@pytest.mark.parametrize("text,kinds", [
    ("Rated 4.8/5 by 12,000 customers.", ["statistic", "reviews"]),
    ("Oltre 500+ recensioni", ["statistic", "reviews"]),
    ("Soddisfatti o rimborsati.", ["guarantee"]),
    ("Designed in Germany, certified", ["authority"]),
    ("Save 20% with our discount", []),                  # a discount is an offer, not proof
    ("Only €336 today", []),                         # a price is not proof
    ("Plain sentence", []),
])
def test_proof_kinds(text, kinds):
    assert copy_analysis.proof_kinds(text) == kinds


def test_full_breakdown(card):
    result = copy_analysis.analyze_ad(parser.parse_card(card))
    assert result["hook"] == {"text": "Still working hunched over a laptop?", "type": "question"}
    assert result["promise"] == {"text": "Raise your desk in 3 seconds."}
    assert result["proof"] == [{"text": "Rated 4.8/5 by 12,000 customers.",
                                "kinds": ["statistic", "reviews"]}]
    assert result["cta"] == {"button": "Shop Now", "kind": "purchase",
                             "closing_line": "\U0001F449 Order today with free shipping",
                             "urgency": True}
    assert result["headline"] == "Sit-stand desk, oak top"
    assert result["structure"] == "hook:question > promise > proof > cta"
    assert result["format"]["emoji"] == 1
    assert result["format"]["mentions_offer"] is True
    assert result["format"]["mentions_price"] is False


def test_breakdown_in_another_language(cards):
    result = copy_analysis.analyze_ad(parser.parse_card(cards[1]))
    assert result["hook"]["type"] == "question"
    assert result["promise"]["text"] == "Scopri la miscela tostata a mano."
    assert result["proof"][0]["kinds"] == ["guarantee"]
    assert result["cta"]["button"] == "Learn more" and result["cta"]["kind"] == "learn"


def test_single_line_and_empty_copy():
    one = copy_analysis.analyze_ad({"library_id": "1", "body": "Hello there", "cta": None})
    assert one["hook"]["type"] == "statement" and one["promise"] is None and one["proof"] == []
    assert one["cta"]["kind"] is None and one["structure"] == "hook:statement"
    empty = copy_analysis.analyze_ad({"library_id": "2", "body": ""})
    assert empty["hook"] is None and empty["structure"] == ""


def test_list_and_price_detection():
    body = "New drop\n✔️ Fast\n✔️ Quiet\nFrom €49"
    fmt = copy_analysis.analyze_ad({"library_id": "1", "body": body})["format"]
    assert fmt["has_list"] and fmt["mentions_price"] and fmt["lines"] == 4


def test_summary_aggregates(cards):
    analyses = [copy_analysis.analyze_ad(ad) for ad in parser.parse_cards(cards)]
    summary = copy_analysis.summarize(analyses)
    assert summary["ads_analyzed"] == 3
    assert summary["hook_types"] == {"question": 3}
    assert summary["share_with_proof"] == 1.0
    assert summary["proof_kinds"] == {"statistic": 2, "reviews": 2, "guarantee": 1}
    assert summary["cta_buttons"] == {"Shop Now": 2, "Learn More": 1}
    assert summary["cta_kinds"] == {"purchase": 2, "learn": 1}
    assert summary["share_with_urgency"] == 0.67
    assert summary["median_characters"] > 0
    assert copy_analysis.summarize([])["ads_analyzed"] == 0
