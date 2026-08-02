from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_adaptive_refinement_execution_contract_v1.json"
SCRIPT = ROOT / "scripts/run_collector_v1_adaptive_refinement_tournaments.py"


def test_contract_exists_and_is_parseable() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_status"] == "PASS_COLLECTOR_ADAPTIVE_REFINEMENT_EXECUTION"
    assert payload["required_refinement_groups"] == 8
    assert payload["required_candidate_rows"] == 2000
    assert payload["finalists_per_group"] == 5


def test_governance_requires_nested_untouched_evidence() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    governance = payload["governance"]
    assert governance["independent_per_horizon"] is True
    assert governance["independent_per_route"] is True
    assert governance["discovery_and_champion_evidence_separate"] is True
    assert governance["product_group_holdout_required"] is True
    assert governance["latest_time_holdout_required"] is True
    assert governance["round1_champion_must_be_challenged"] is True
    assert governance["naive_baseline_must_be_challenged"] is True


def test_current_only_features_and_purchase_gates_remain_closed() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    governance = payload["governance"]
    assert governance["current_only_features_prohibited"] is True
    assert governance["production_forecasting_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_365_day_objective_includes_early_growth_detection() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    weights = payload["365_day_objective_weights"]
    assert weights["major_grower_recall"] > 0
    assert weights["major_grower_precision"] > 0
    assert weights["early_detection_rate"] > 0
    assert round(sum(weights.values()), 10) == 1.0


def test_standard_objective_weights_sum_to_one() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert round(sum(payload["standard_objective_weights"].values()), 10) == 1.0


def test_script_contains_required_fail_closed_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = [
        "INNER_DISCOVERY",
        "OUTER_CHAMPION",
        "stable_bucket",
        "multiple_testing_penalty",
        "ROUND2_FINALIST_ADVANCES",
        "RETAIN_ROUND1_CHAMPION",
        '"current_only_features_used": False',
        '"production_forecasting_authorized": False',
        '"purchase_recommendations_authorized": False',
    ]
    for token in required:
        assert token in text


def test_script_emits_required_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for name in [
        "collector_round2_candidate_scores.csv",
        "collector_round2_finalists.csv",
        "collector_round2_outer_predictions.csv",
        "collector_round2_champion_challenge_registry.csv",
        "collector_adaptive_refinement_execution_summary.json",
    ]:
        assert name in text
