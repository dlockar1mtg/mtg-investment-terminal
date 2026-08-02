from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_production_forecast_overlay_ranking_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_production_forecast_overlay_ranking.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_and_script_exist() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()


def test_round3_dependency_is_exact() -> None:
    contract = load_contract()
    assert contract["required_round3_status"] == "PASS_COLLECTOR_ROUND3_FINAL_CHAMPION_CHALLENGE"
    assert contract["required_certified_champion_groups"] == 6
    assert contract["required_preserved_no_winner_groups"] == 10


def test_uncertainty_is_required() -> None:
    contract = load_contract()
    assert contract["governance"]["uncertainty_required_for_every_forecast"] is True
    assert contract["uncertainty"]["blocked_group_interval_allowed"] is False
    assert contract["uncertainty"]["minimum_relative_half_width"] > 0


def test_overlay_is_post_forecast_only() -> None:
    contract = load_contract()
    assert contract["governance"]["current_supply_demand_post_forecast_only"] is True
    assert contract["governance"]["current_supply_demand_cannot_create_forecast"] is True
    assert contract["overlay"]["historical_backtest_use_allowed"] is False
    assert contract["overlay"]["point_forecast_rewrite_allowed"] is False


def test_overlay_adjustment_is_bounded() -> None:
    contract = load_contract()
    assert 0 < contract["overlay"]["maximum_absolute_conviction_adjustment"] <= 0.15
    assert 0 < contract["overlay"]["minimum_feature_coverage"] <= 1


def test_ranking_weights_sum_to_one() -> None:
    ranking = load_contract()["ranking"]
    weights = [
        ranking["forecast_return_weight"],
        ranking["downside_weight"],
        ranking["validation_weight"],
        ranking["early_opportunity_weight"],
        ranking["supply_demand_weight"],
    ]
    assert abs(sum(weights) - 1.0) < 1e-9


def test_blocked_products_cannot_be_ranked() -> None:
    contract = load_contract()
    assert contract["ranking"]["rank_blocked_products"] is False
    assert contract["governance"]["ranking_requires_at_least_one_certified_forecast"] is True


def test_purchase_authorization_remains_closed() -> None:
    contract = load_contract()
    assert contract["ranking"]["purchase_authorization_allowed"] is False
    assert contract["governance"]["purchase_recommendations_authorized"] is False


def test_script_contains_required_outputs_and_guards() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "collector_production_forecasts.csv",
        "collector_supply_demand_overlays.csv",
        "collector_governed_rankings.csv",
        "collector_forecast_blocked_products.csv",
        "collector_production_forecast_overlay_ranking_summary.json",
        "CURRENT_SUPPLY_SNAPSHOT_NOT_FOUND",
        "SUPPLY_OVERLAY_COVERAGE_BELOW_MINIMUM",
        "OVERLAY_REWROTE_POINT_FORECAST",
        "PURCHASE_PREMATURELY_AUTHORIZED",
    ]:
        assert token in text
