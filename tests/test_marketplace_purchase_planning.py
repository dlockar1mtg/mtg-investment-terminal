from __future__ import annotations

from terminal2.market_sources.marketplace_purchase_planning import PurchasePolicy, build_purchase_plan


def _model(product_id: str, investment_id: str, name: str) -> dict[str, str]:
    return {
        "tcgplayer_product_id": product_id,
        "investment_product_id": investment_id,
        "box_name": name,
        "current_price": "400",
    }


def _decision(product_id: str, name: str, price: float, signal: str, score: float = 40.0) -> dict[str, object]:
    return {
        "tcgplayer_product_id": product_id,
        "product_name": name,
        "consolidated_market_price": price,
        "signal": signal,
        "allocation_action": "ACCUMULATE_PRIORITY" if signal == "STRONG_BUY" else "ACCUMULATE",
        "deal_score": score,
        "suggested_new_capital_min_pct": 35 if signal == "STRONG_BUY" else 15,
        "suggested_new_capital_max_pct": 50 if signal == "STRONG_BUY" else 30,
    }


def test_bootstrap_plan_buys_one_whole_box_and_preserves_reserve() -> None:
    plan, projections, summary = build_purchase_plan(
        [_decision("271509", "Double Masters 2022", 434.07, "STRONG_BUY")],
        [_model("271509", "TCGCSV-3070-271509", "Double Masters 2022")],
        [],
        PurchasePolicy(monthly_capital=600, reserve_pct=10),
    )

    assert summary["status"] == "PASS"
    assert summary["planned_spend"] == 434.07
    assert summary["unspent_capital"] == 165.93
    assert summary["reserve_preserved"] is True
    assert summary["total_units"] == 1
    assert plan[0]["recommended_units"] == 1
    assert plan[0]["plan_action"] == "BUY_NOW"
    assert plan[0]["whole_unit_band_exception"] is True
    assert projections[0]["projected_quantity"] == 1


def test_watch_decisions_receive_no_new_capital() -> None:
    plan, _, summary = build_purchase_plan(
        [_decision("618893", "Final Fantasy", 300, "WATCH")],
        [_model("618893", "TCGCSV-24219-618893", "Final Fantasy")],
        [],
        PurchasePolicy(monthly_capital=600),
    )

    assert plan == []
    assert summary["status"] == "NO_ACTION"
    assert summary["planned_spend"] == 0
    assert summary["carry_forward_capital"] == 600


def test_unaffordable_whole_box_is_carried_forward() -> None:
    plan, _, summary = build_purchase_plan(
        [_decision("484912", "Lord of the Rings", 900, "STRONG_BUY")],
        [_model("484912", "TCGCSV-23019-484912", "Lord of the Rings")],
        [],
        PurchasePolicy(monthly_capital=600, reserve_pct=10),
    )

    assert summary["status"] == "PASS"
    assert summary["planned_spend"] == 0
    assert summary["carry_forward_capital"] == 600
    assert "CAPITAL_CARRIED_FORWARD_NO_FEASIBLE_WHOLE_UNIT_PURCHASE" in summary["reason_codes"]
    assert plan[0]["plan_action"] == "CARRY_FORWARD_INSUFFICIENT_CAPITAL"


def test_existing_holdings_concentration_can_block_an_additional_unit() -> None:
    decisions = [
        _decision("111", "Existing Heavy Position", 300, "STRONG_BUY", 50),
        _decision("222", "Diversifier", 250, "BUY", 30),
    ]
    models = [
        _model("111", "INV-111", "Existing Heavy Position"),
        _model("222", "INV-222", "Diversifier"),
    ]
    holdings = [{
        "investment_product_id": "INV-111",
        "quantity": "4",
        "acquisition_cost_total": "1000",
        "acquisition_date": "2026-01-01",
        "notes": "",
    }]

    plan, projections, summary = build_purchase_plan(
        decisions,
        models,
        holdings,
        PurchasePolicy(
            monthly_capital=600,
            reserve_pct=0,
            max_projected_product_weight_pct=71,
            bootstrap_portfolio_value_threshold=0,
        ),
    )

    by_id = {row["tcgplayer_product_id"]: row for row in plan}
    assert summary["status"] == "PASS"
    assert by_id["111"]["recommended_units"] == 0
    assert by_id["222"]["recommended_units"] == 2
    assert max(row["projected_portfolio_weight_pct"] for row in projections) <= 71.0


def test_unknown_holding_product_id_fails_closed() -> None:
    _, _, summary = build_purchase_plan(
        [_decision("271509", "Double Masters 2022", 434.07, "STRONG_BUY")],
        [_model("271509", "INV-271509", "Double Masters 2022")],
        [{"investment_product_id": "UNKNOWN", "quantity": "1", "acquisition_cost_total": "100"}],
        PurchasePolicy(monthly_capital=600),
    )

    assert summary["status"] == "INCOMPLETE"
    assert summary["unknown_holding_product_ids"] == ["UNKNOWN"]
