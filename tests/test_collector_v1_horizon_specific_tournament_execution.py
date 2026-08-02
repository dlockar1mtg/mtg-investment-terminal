from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_horizon_tournament_execution_contract_v1.json"
SCRIPT = ROOT / "scripts/run_collector_v1_horizon_specific_tournaments.py"


def test_contract_defines_six_independent_horizons() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert [row["days"] for row in payload["horizons"]] == [90, 180, 365, 730, 1095, 1825]
    assert payload["winner_selection"]["independent_winner_per_horizon_and_route"] is True


def test_estimated_price_band_is_not_a_hard_standard() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    definition = payload["major_365_growth_definition"]
    assert "350-400" in definition["description"]
    assert "not a gate" in definition["description"]
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"price_band_gate_used": False' in text
    assert '"price_band_used_as_hard_gate": False' in text


def test_major_growth_is_relative_and_absolute() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    definition = payload["major_365_growth_definition"]
    assert definition["absolute_return_floor"] == 0.50
    assert definition["cross_product_quantile"] == 0.75
    assert "max(absolute_return_floor" in definition["classification_rule"]


def test_early_detection_requires_signal_before_most_upside() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    definition = payload["major_365_growth_definition"]
    assert definition["early_origin_max_age_days"] == 180
    assert definition["maximum_upside_already_captured"] == 0.40
    assert definition["maximum_origin_to_day365_price_ratio"] == 0.70
    text = SCRIPT.read_text(encoding="utf-8")
    assert "upside_already_captured_at_signal" in text
    assert "early_detection_success" in text
    assert "late_signal" in text
    assert "false_positive" in text


def test_current_supply_demand_stays_out_of_backtests() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    policy = payload["current_supply_demand_policy"]
    assert policy["historical_fit_allowed"] is False
    assert policy["historical_backtest_allowed"] is False
    assert policy["post_forecast_overlay_allowed"] is True
    assert policy["point_forecast_rewrite_allowed"] is False
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"current_only_features_used": False' in text
    assert '"current_supply_demand_used_in_backtest": False' in text


def test_script_uses_rolling_origin_and_future_tolerance() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "nearest_future" in text
    assert "future_match_tolerance_days" in text
    assert "origin_index" in text
    assert "training_observations" in text


def test_route_specific_model_families_are_distinct() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "EXPONENTIAL_SMOOTHING" in payload["direct_calibrated_models"]
    assert "EXPONENTIAL_SMOOTHING" not in payload["direct_limited_models"]
    assert "COMPARABLE_SHRUNK_ENSEMBLE" in payload["comparable_models"]


def test_expected_outputs_are_named() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for name in [
        "collector_rolling_origin_predictions.csv",
        "collector_model_tournament_scores.csv",
        "collector_horizon_route_winners.csv",
        "collector_365_day_early_growth_detection.csv",
        "collector_365_day_early_growth_metrics.csv",
        "collector_horizon_specific_tournament_execution_summary.json",
    ]:
        assert name in text


def test_production_and_purchase_gates_remain_closed() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["production_forecasting_authorized"] is False
    assert payload["purchase_recommendations_authorized"] is False
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"production_forecasting_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text
