from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_adaptive_tournament_refinement_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_adaptive_tournament_refinement_architecture.py"


def test_contract_requires_multi_round_refinement() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["rounds"]["round_1"]
    assert payload["rounds"]["round_2"]
    assert payload["rounds"]["round_3"]
    assert payload["minimum_refinement_candidates_per_eligible_group"] >= 40
    assert payload["maximum_refinement_candidates_per_eligible_group"] >= 200


def test_contract_requires_independent_horizon_and_route_refinement() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["independent_refinement_per_horizon"] is True
    assert payload["independent_refinement_per_route"] is True
    assert payload["forecast_horizons_days"] == [90, 180, 365, 730, 1095, 1825]


def test_contract_prevents_metric_discovery_overfit() -> None:
    controls = json.loads(CONTRACT.read_text(encoding="utf-8"))["anti_overfit_controls"]
    assert controls["nested_rolling_origin_required"] is True
    assert controls["discovery_and_champion_folds_separate"] is True
    assert controls["product_group_holdout_required"] is True
    assert controls["multiple_testing_penalty_required"] is True
    assert controls["round_1_champion_challenge_required"] is True


def test_current_only_features_remain_prohibited() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prohibited = set(payload["current_only_features_prohibited_from_refinement"])
    assert "ebay_listing_count" in prohibited
    assert "ebay_seller_count" in prohibited
    assert "current_scarcity_tier" in prohibited
    assert "august1_current_price" in prohibited


def test_365_day_objective_includes_early_growth_quality() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    metrics = set(payload["selection_objectives"]["365_day_additional"])
    assert "major_grower_precision" in metrics
    assert "major_grower_recall" in metrics
    assert "early_detection_rate" in metrics
    assert "late_signal_rate" in metrics
    assert "false_positive_rate" in metrics
    assert "upside_remaining_at_signal" in metrics


def test_script_builds_large_candidate_registry_and_keeps_promotion_closed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "collector_refinement_candidate_registry.csv" in text
    assert "collector_refinement_group_registry.csv" in text
    assert "INNER_DISCOVERY" in text
    assert "OUTER_UNTOUCHED_CHALLENGE" in text
    assert '"production_forecasting_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text
