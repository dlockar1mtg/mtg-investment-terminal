import json

from scripts.certify_full_universe_counts import check, main

GOOD = {"booster_display_count": 235, "secret_lair_count": 993, "total_marketplace_products": 1228,
        "ebay_ready_count": 1228, "tcgcsv_ready_count": 1217, "ebay_only_count": 11, "review_excluded_count": 15}


def test_growth_passes():
    assert check(GOOD) == []


def test_totals_must_add_up():
    bad = {**GOOD, "secret_lair_count": 994}
    assert any("Secret Lairs" in e for e in check(bad))


def test_every_product_must_be_ebay_ready():
    assert any("eBay-ready" in e for e in check({**GOOD, "ebay_ready_count": 1200}))


def test_sharp_drop_fails():
    shrunk = {**GOOD, "booster_display_count": 100, "total_marketplace_products": 1093,
              "ebay_ready_count": 1093, "tcgcsv_ready_count": 1082}
    assert any("below" in e for e in check(shrunk))


def test_missing_field_fails():
    assert check({k: v for k, v in GOOD.items() if k != "ebay_only_count"})


def test_main_reads_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(GOOD))
    assert main(p) == 0
