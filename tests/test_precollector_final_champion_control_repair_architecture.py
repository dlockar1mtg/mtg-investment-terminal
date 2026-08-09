from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_final_champion_control_repair_architecture_contract_v1.json"
SCRIPT = ROOT / "scripts/build_precollector_final_champion_control_repair_architecture.py"


def load_module():
    spec = importlib.util.spec_from_file_location("control_repair_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_id"] == "precollector_final_champion_control_repair_architecture_v1"


def test_package_hash_is_bound():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["required_final_challenge_package"]["sha256"] == "7cc9c8ec5adb4d57bf81156c00b36537ae65077dcceabe295cc1b1f8f2296ca3"


def test_expected_counts_are_frozen():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_counts"] == {
        "short_horizon_challenge_groups": 9,
        "frozen_candidate_rows": 30,
        "candidate_partition_scorecard_rows": 90,
        "final_group_decision_rows": 9,
        "long_horizon_monte_carlo_routes": 6,
    }


def test_v1_decisions_are_superseded_not_deleted():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["superseded_decision_status"] == "SUPERSEDED_PENDING_CONTROL_DESIGN_REPAIR"
    assert payload["prohibited_behavior"]["modify_existing_execution_package"] is True


def test_candidate_and_evidence_immutability_required():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    principles = payload["repair_principles"]
    assert principles["preserve_candidate_set"] is True
    assert principles["preserve_fold_membership"] is True
    assert principles["preserve_prediction_error_evidence"] is True


def test_no_new_tuning_is_allowed():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    principles = payload["repair_principles"]
    assert principles["no_new_model_tuning"] is True
    assert principles["no_new_feature_tuning"] is True
    assert principles["no_threshold_selection_to_force_winners"] is True


def test_outer_all_is_primary_eligibility_partition():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    outer = payload["repaired_control_design"]["outer_all"]
    assert outer["role"] == "PRIMARY_PRODUCTION_ELIGIBILITY"
    assert "maximum_mean_signed_percentage_error" in outer


def test_latest_time_bias_is_not_a_hard_rejection():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    latest = payload["repaired_control_design"]["latest_time_stress"]
    assert latest["role"] == "ROBUSTNESS_ONLY"
    assert latest["hard_bias_rejection_authorized"] is False


def test_concentration_partition_does_not_recursively_reject_concentration():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    concentration = payload["repaired_control_design"]["product_concentration_stress"]
    assert concentration["recursive_concentration_rejection_authorized"] is False
    assert concentration["recursive_worst_product_rejection_authorized"] is False


def test_execution_stage_is_control_recalculation_only():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prohibited = payload["prohibited_behavior"]
    assert prohibited["recompute_predictions"] is True
    assert prohibited["recompute_errors"] is True
    assert prohibited["change_candidates"] is True
    assert prohibited["change_folds"] is True


def test_downstream_authority_remains_false():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["final_winner_certification_authorized"] is False
    assert payload["forecast_generation_authorized"] is False
    assert payload["ranking_execution_authorized"] is False
    assert payload["purchase_analysis_authorized"] is False


def test_module_loads():
    module = load_module()
    assert callable(module.main)
