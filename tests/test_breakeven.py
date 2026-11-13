import pytest

from ad_library_insights import breakeven


def test_breakeven_cpa_formula():
    # 60 - 20 - 5 - 3% of 60 (1.80) - 0.30 - 2 = 30.90
    assert breakeven.breakeven_cpa(60, 20, 5, 3, 0.30, 2) == 30.90
    assert breakeven.breakeven_cpa(50) == 50
    with pytest.raises(ValueError):
        breakeven.breakeven_cpa(0)


@pytest.mark.parametrize("spend,atc,purchases,verdict", [
    (75, 0, 0, "cut"),       # 2.5x, no signal at all
    (90, 0, 0, "cut"),
    (74, 0, 0, "watch"),     # just under the threshold
    (90, 4, 0, "review"),    # add to carts but nobody buys
    (30, 0, 0, "watch"),     # 1x
    (10, 0, 0, "wait"),
    (60, 5, 3, "keep"),      # CPA 20 <= 30
    (120, 9, 2, "review"),   # CPA 60 > 30
])
def test_verdicts_at_breakeven_30(spend, atc, purchases, verdict):
    assert breakeven.judge_ad(spend, atc, purchases, breakeven=30, multiplier=2.5)[0] == verdict


def test_multiplier_is_a_parameter():
    assert breakeven.judge_ad(60, 0, 0, 30, multiplier=2)[0] == "cut"
    assert breakeven.judge_ad(60, 0, 0, 30, multiplier=3)[0] == "watch"


def test_unprofitable_product_is_rejected():
    with pytest.raises(ValueError):
        breakeven.judge_ad(10, 0, 0, breakeven=-5)


def test_evaluate_sorts_cuts_first_and_adds_metrics():
    rows = [
        {"name": "winner", "spend": 60, "add_to_cart": 5, "purchases": 3},
        {"name": "dead", "spend": 80, "add_to_cart": 0, "purchases": 0},
        {"name": "young", "spend": 5},
    ]
    judged = breakeven.evaluate_ads(rows, 30)
    assert [r["name"] for r in judged] == ["dead", "young", "winner"]
    assert judged[0]["spend_vs_breakeven"] == 2.67 and judged[0]["cpa"] is None
    assert judged[2]["cpa"] == 20


@pytest.mark.parametrize("raw,value", [("1,234.50", 1234.5), ("1.234,50", 1234.5), ("€ 12", 12.0),
                                       ("12,5", 12.5), ("", 0.0), ("7", 7.0)])
def test_number_parsing(raw, value):
    assert breakeven._number(raw) == value


def test_load_english_export(tmp_path):
    path = tmp_path / "ads.csv"
    path.write_text("Ad name,Amount spent (EUR),Adds to cart,Purchases\nA,80.00,0,\nB,60,5,3\n",
                    encoding="utf-8")
    assert breakeven.load_ads_csv(path) == [
        {"name": "A", "spend": 80.0, "add_to_cart": 0.0, "purchases": 0.0},
        {"name": "B", "spend": 60.0, "add_to_cart": 5.0, "purchases": 3.0},
    ]


def test_load_italian_semicolon_export(tmp_path):
    path = tmp_path / "ads.csv"
    path.write_text("Nome dell'inserzione;Importo speso (EUR);Aggiunte al carrello;Acquisti\n"
                    "Video 1;\"80,50\";0;0\n", encoding="utf-8-sig")
    assert breakeven.load_ads_csv(path) == [
        {"name": "Video 1", "spend": 80.5, "add_to_cart": 0.0, "purchases": 0.0}]


def test_csv_without_spend_column_fails(tmp_path):
    path = tmp_path / "ads.csv"
    path.write_text("Ad name,Clicks\nA,3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        breakeven.load_ads_csv(path)
