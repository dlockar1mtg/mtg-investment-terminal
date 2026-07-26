from __future__ import annotations

from terminal2.market_sources.marketplace_decisioning import build_decisions, consolidate_certified_rows


def test_certified_sources_consolidate_by_tcgplayer_id() -> None:
    consolidated = consolidate_certified_rows([
        {
            "tcgplayer_product_id": "271509",
            "product_name": "Double Masters 2022",
            "source_name": "TCGCSV",
            "certified_price": "432.65",
            "eligible_for_decisioning": "true",
        },
        {
            "tcgplayer_product_id": "271509",
            "product_name": "Double Masters 2022",
            "source_name": "EBAY",
            "certified_price": "435.49",
            "eligible_for_decisioning": "true",
        },
        {
            "tcgplayer_product_id": "271509",
            "source_name": "OTHER",
            "certified_price": "1",
            "eligible_for_decisioning": "false",
        },
    ])

    assert len(consolidated) == 1
    row = consolidated[0]
    assert row["consolidated_price"] == 434.07
    assert row["source_count"] == 2
    assert row["source_names"] == "EBAY|TCGCSV"
    assert row["price_quality_state"] == "MULTI_SOURCE_CERTIFIED"


def test_decisions_use_mc_median_and_certified_current_price() -> None:
    consolidated = [{
        "tcgplayer_product_id": "271509",
        "product_name": "Double Masters 2022",
        "consolidated_price": 434.07,
        "source_count": 2,
        "source_names": "EBAY|TCGCSV",
        "cross_source_spread_pct": 0.66,
        "price_quality_state": "MULTI_SOURCE_CERTIFIED",
    }]
    model = [{
        "tcgplayer_product_id": "271509",
        "box_name": "Double Masters 2022 Collector Booster Display",
        "current_price": "410.80",
        "fair_value_estimate": "410.80",
        "mc_median": "526.00",
        "mc_expected_value": "540.00",
        "data_quality_score": "90",
        "liquidity_score": "80",
        "reprint_risk": "30",
        "prob_loss": "0.10",
        "prob_double": "0.20",
    }]

    decisions, summary = build_decisions(consolidated, model)

    assert summary["status"] == "PASS"
    assert summary["decision_count"] == 1
    row = decisions[0]
    assert row["forecast_anchor"] == 526.0
    assert row["forecast_anchor_type"] == "MC_MEDIAN"
    assert row["consolidated_market_price"] == 434.07
    assert row["expected_upside_pct"] == 21.18
    assert row["signal"] == "BUY"
    assert "CROSS_SOURCE_CONFIRMED" in row["decision_reason_codes"]


def test_unmatched_certified_product_is_reported_fail_closed() -> None:
    decisions, summary = build_decisions([
        {
            "tcgplayer_product_id": "999999",
            "consolidated_price": 100,
            "source_count": 1,
            "source_names": "EBAY",
            "cross_source_spread_pct": 0,
        }
    ], [])

    assert decisions == []
    assert summary["status"] == "INCOMPLETE"
    assert summary["unmatched_certified_product_ids"] == ["999999"]
