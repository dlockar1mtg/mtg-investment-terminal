from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_adaptive_tournament_refinement_architecture_contract_v1.json"
BUILDER = ROOT / "scripts/build_precollector_adaptive_tournament_refinement_architecture.py"


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_binds_certified_round_one_package() -> None:
    package = contract()["required_round_one_package"]
    assert package["package_name"] == "MTG_PreCollector_Horizon_Tournament_Execution_From_Certified_Bundle_v1.zip"
    assert package["sha256"] == "0088ddd5f1a87c12eb720956c75605f821aafa6d2e495d2b4c291065080ec231"


def test_contract_binds_round_one_counts() -> None:
    assert contract()["expected_round_one_counts"] == {
        "active_products": 79,
        "horizons": 5,
        "routes": 3,
        "tournament_groups": 15,
        "competitive_winners": 9,
        "governed_fallbacks": 6,
        "rolling_predictions": 9162,
        "model_scorecards": 39,
        "uncertainty_rows": 15,
    }


def test_contract_requires_all_round_one_evidence() -> None:
    members = set(contract()["required_round_one_members"])
    assert "precollector_round_one_rolling_predictions.csv" in members
    assert "precollector_round_one_model_scorecard.csv" in members
    assert "precollector_round_one_preliminary_winner_registry.csv" in members
    assert "precollector_round_one_uncertainty_evidence.csv" in members
    assert "precollector_round_one_certified_input_lineage.csv" in members


def test_contract_refines_competitive_and_fallback_groups() -> None:
    advancement = contract()["advancement"]
    assert advancement["competitive_group_preserve_round_one_winner"] is True
    assert advancement["competitive_group_preserve_naive_baseline"] is True
    assert advancement["fallback_group_include_all_round_one_models"] is True
    assert advancement["fallback_group_preserve_governed_fallback"] is True
    assert advancement["fallback_group_mode"] == "EVIDENCE_RECOVERY_CHALLENGE"
    assert advancement["no_forced_winner"] is True


def test_contract_has_model_specific_parameter_grids() -> None:
    grids = contract()["parameter_grids"]
    for model in [
        "NAIVE_LAST_VALUE", "DRIFT", "ROBUST_LOG_LINEAR", "DAMPED_TREND",
        "EXPONENTIAL_SMOOTHING", "RANK_DECAY_WEIGHTED_GROWTH",
        "LIFECYCLE_MATCHED_COMPARABLE", "SHRUNK_COMPARABLE_ENSEMBLE",
    ]:
        assert model in grids
        assert grids[model]


def test_contract_requires_boundary_expansion() -> None:
    policy = contract()["boundary_expansion"]
    assert policy["required_when_best_parameter_is_grid_minimum_or_maximum"] is True
    assert policy["maximum_expansion_rounds"] == 2
    assert policy["retain_original_grid"] is True


def test_contract_requires_anti_overfit_controls() -> None:
    controls = contract()["anti_overfit_controls"]
    for key in [
        "nested_rolling_origin_required", "discovery_and_champion_folds_separate",
        "product_group_holdout_required", "multiple_testing_penalty_required",
        "complexity_penalty_required", "baseline_challenge_required",
        "round_one_champion_challenge_required", "parameter_boundary_review_required",
        "uncertainty_recalibration_required",
    ]:
        assert controls[key] is True


def test_contract_preserves_downstream_blocks() -> None:
    data = contract()
    assert data["refinement_execution_authorized"] is True
    for key in [
        "final_winner_certification_authorized", "forecast_generation_authorized",
        "ranking_execution_authorized", "purchase_analysis_authorized",
        "purchase_recommendation_authorized", "automatic_purchase_execution_authorized",
        "uip_delivery_authorized",
    ]:
        assert data[key] is False


def test_builder_is_architecture_only() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "requests" not in text
    assert "urlopen" not in text
    assert "REFINEMENT_EXECUTION_PERFORMED=FALSE" in text
    assert "zipfile.ZipFile" in text
    assert "parameter_combinations" in text
    assert "EVIDENCE_RECOVERY_CHALLENGE" not in text or "fallback_group_mode" in text


def test_builder_preserves_round_one_folds() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "CERTIFIED_ROUND_ONE_ROLLING_PREDICTIONS" in text
    assert '"fold_membership_mutable": False' in text
    assert "OUTER_UNTOUCHED_CHALLENGE" in text


def test_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_round_two_architecture", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
