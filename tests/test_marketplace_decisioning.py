from __future__ import annotations

from terminal2.market_sources.marketplace_decisioning import (
    POLICY_VERSION,
    build_decisions,
    consolidate_certified_rows,
)


def _price(product_id: str, price: float, *, sources: int = 2, spread: float = 2.0) -> dict[str, object]:
    return {
        "tcgplayer_product_id": product_id,
        "product_name": f"Product {product_id}",
        "consolidated_price": price,
        "source_count": sources,
        "source_names": "EBAY|TCGCSV" if sources >= 2 else "TCGCSV",
        "cross_source_spread_pct": spread,
        "price_quality_state": "MULTI_SOURCE_CERTIFIED" if sources >= 2 else "SINGLE_SOURCE_CERTIFIED",
    }


def _model(
    product_id: str,
    anchor: float,
    *,
    quality: float = 90,
    liquidity: float = 80,
    reprint: float = 30,
    prob_loss: float = 0.10,
) -> dict[str, str]:
    return {
        "tcgplayer_product_id": product_id,
        "box_name": f"Product {product_id}",
        "mc_median": str(anchor),
        "mc_expected_value": str(anchor * 1.05),
        "fair_value_estimate": str(anchor * 0.90),
        "data_quality_score": str(quality),
        "liquidity_score": str(liquidity),
        "reprint_risk": str(reprint),
        "prob_loss": str(prob_loss),
        "prob_double": "0.20",
    }


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


def test_decisions_use_mc_median_and_publish_allocation_policy() -> None:
    decisions, summary = build_decisions([_price("271509", 434.07)], [_model("271509", 526.00)])

    assert summary["status"] == "PASS"
    assert summary["policy_version"] == POLICY_VERSION
    row = decisions[0]
    assert row["forecast_anchor"] == 526.0
    assert row["forecast_anchor_type"] == "MC_MEDIAN"
    assert row["expected_upside_pct"] == 21.18
    assert row["base_signal"] == "BUY"
    assert row["signal"] == "BUY"
    assert row["allocation_action"] == "ACCUMULATE"
    assert row["suggested_new_capital_min_pct"] == 15.0
    assert row["suggested_new_capital_max_pct"] == 30.0
    assert row["policy_override_applied"] is False


def test_high_loss_probability_caps_buy_at_watch() -> None:
    decisions, summary = build_decisions(
        [_price("484912", 100.0)],
        [_model("484912", 130.0, prob_loss=0.35)],
    )

    row = decisions[0]
    assert row["base_signal"] == "STRONG_BUY"
    assert row["signal"] == "WATCH"
    assert row["allocation_action"] == "WAIT_FOR_CONFIRMATION"
    assert row["suggested_new_capital_max_pct"] == 0.0
    assert row["policy_override_applied"] is True
    assert "POLICY_LOSS_RISK_CAP_WATCH" in row["decision_reason_codes"]
    assert summary["policy_override_count"] == 1
    assert summary["deployable_decision_count"] == 0


def test_single_source_and_large_spread_do_not_receive_buy_signal() -> None:
    decisions, _ = build_decisions(
        [_price("1", 100.0, sources=1, spread=30.0)],
        [_model("1", 140.0)],
    )

    row = decisions[0]
    assert row["base_signal"] == "STRONG_BUY"
    assert row["signal"] == "WATCH"
    assert "POLICY_SINGLE_SOURCE_CAP_WATCH" in row["decision_reason_codes"]


def test_rank_order_is_consistent_with_policy_signal_before_score() -> None:
    decisions, _ = build_decisions(
        [_price("buy", 100.0), _price("watch", 100.0)],
        [
            _model("buy", 118.0, quality=50, liquidity=40, prob_loss=0.01),
            _model("watch", 140.0, quality=100, liquidity=100, prob_loss=0.40),
        ],
    )

    assert decisions[0]["tcgplayer_product_id"] == "buy"
    assert decisions[0]["signal"] == "BUY"
    assert decisions[1]["tcgplayer_product_id"] == "watch"
    assert decisions[1]["signal"] == "WATCH"


def test_low_quality_caps_positive_upside_at_hold() -> None:
    decisions, _ = build_decisions(
        [_price("low-quality", 100.0)],
        [_model("low-quality", 140.0, quality=45)],
    )

    row = decisions[0]
    assert row["base_signal"] == "STRONG_BUY"
    assert row["signal"] == "HOLD"
    assert row["allocation_action"] == "MAINTAIN_ONLY"
    assert "POLICY_DATA_OR_LIQUIDITY_CAP_HOLD" in row["decision_reason_codes"]


def test_unmatched_certified_product_is_reported_fail_closed() -> None:
    decisions, summary = build_decisions([_price("999999", 100)], [])

    assert decisions == []
    assert summary["status"] == "INCOMPLETE"
    assert summary["unmatched_certified_product_ids"] == ["999999"]
