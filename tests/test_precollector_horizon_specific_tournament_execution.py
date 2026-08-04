from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_horizon_specific_tournament_execution_contract_v1.json"
BUILDER = ROOT / "scripts/build_precollector_horizon_specific_tournament_execution.py"


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_requires_five_horizons_and_three_routes() -> None:
    data = contract()
    assert data["expected_horizon_count"] == 5
    assert data["expected_route_count"] == 3
    assert data["expected_winner_rows"] == 15


def test_contract_requires_79_products() -> None:
    assert contract()["expected_active_product_count"] == 79


def test_contract_has_fail_closed_fallbacks() -> None:
    fallbacks = contract()["fallback_models"]
    assert fallbacks["DIRECT_HISTORY_CALIBRATED"] == "NAIVE_LAST_VALUE"
    assert fallbacks["DIRECT_HISTORY_LIMITED"] == "NAIVE_LAST_VALUE"
    assert fallbacks["COMPARABLE_PRODUCT_ADJUSTED"] == "RANK_DECAY_WEIGHTED_GROWTH"


def test_contract_preserves_all_downstream_blocks() -> None:
    data = contract()
    for key in [
        "forecast_generation_authorized", "ranking_execution_authorized",
        "purchase_analysis_authorized", "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized", "uip_delivery_authorized",
    ]:
        assert data[key] is False


def test_contract_advances_only_to_winner_certification() -> None:
    assert contract()["next_stage_if_certified"] == "PRECOLLECTOR_HORIZON_WINNER_AND_UNCERTAINTY_CERTIFICATION"


def test_builder_requires_rolling_origin_predictions() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "NO_ROLLING_ORIGIN_PREDICTIONS" in text
    assert "nearest_future" in text
    assert "origin_date" in text


def test_builder_selects_winners_independently_by_horizon_and_route() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert 'for horizon in architecture["horizon_code"].tolist()' in text
    assert 'for route in sorted(products["forecast_method"].unique())' in text
    assert "INCOMPLETE_HORIZON_ROUTE_WINNER_COVERAGE" in text


def test_builder_calibrates_uncertainty() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "calibrated_log_uncertainty" in text
    assert "MAXIMUM_UNCERTAINTY_FALLBACK" in text
    assert "CALIBRATED_FROM_ROLLING_ORIGIN_ERRORS" in text


def test_builder_keeps_forecast_authority_false() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert '"forecast_generation_authorized": False' in text
    assert 'print("FORECAST_AUTHORIZED=FALSE")' in text


def test_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_horizon_execution", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
