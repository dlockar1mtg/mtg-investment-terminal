from __future__ import annotations

from terminal2.market_sources.marketplace_quality import certify_rows


def test_ebay_low_price_outlier_is_quarantined_without_rejecting_median() -> None:
    rows, summary = certify_rows([{
        "source_name": "EBAY",
        "product_name": "10th Edition Booster Box",
        "tcgplayer_product_id": "27257",
        "market_price": "965",
        "median_price": "965",
        "low_price": "20",
        "listing_count": "3",
        "seller_count": "3",
        "confidence": "70",
    }])
    row = rows[0]
    assert row["low_price"] == ""
    assert row["certified_price"] == 965.0
    assert row["quality_state"] == "CERTIFIED_WITH_WARNING"
    assert row["eligible_for_decisioning"] == "true"
    assert "EBAY_LOW_PRICE_OUTLIER_QUARANTINED" in row["quality_reason_codes"]
    assert summary["eligible_observation_count"] == 1


def test_cross_source_divergence_quarantines_ebay_observation() -> None:
    rows, summary = certify_rows([
        {
            "source_name": "TCGCSV",
            "tcgplayer_product_id": "1",
            "market_price": "100",
            "median_price": "100",
            "confidence": "100",
        },
        {
            "source_name": "EBAY",
            "tcgplayer_product_id": "1",
            "market_price": "200",
            "median_price": "200",
            "low_price": "190",
            "listing_count": "5",
            "seller_count": "4",
            "confidence": "90",
        },
    ])
    ebay = next(row for row in rows if row["source_name"] == "EBAY")
    assert ebay["quality_state"] == "QUARANTINED"
    assert ebay["eligible_for_decisioning"] == "false"
    assert "CROSS_SOURCE_PRICE_DIVERGENCE" in ebay["quality_reason_codes"]
    assert summary["quarantined_observation_count"] == 1


def test_tcgcsv_market_observation_is_certified() -> None:
    rows, summary = certify_rows([{
        "source_name": "TCGCSV",
        "tcgplayer_product_id": "1",
        "market_price": "432.65",
        "median_price": "526.00",
        "confidence": "100",
    }])
    assert rows[0]["quality_state"] == "CERTIFIED"
    assert rows[0]["eligible_for_decisioning"] == "true"
    assert summary["status"] == "PASS"
