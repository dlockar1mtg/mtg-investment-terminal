from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_winner_uncertainty_certification_architecture.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_winner_uncertainty_certification_architecture_contract_v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("winner_uncertainty_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_id"] == "precollector_winner_uncertainty_certification_architecture_v1"


def test_contract_binds_certified_repair_execution_hash():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["required_control_repair_execution_package"]["sha256"] == "fcdc8843f5c9ba0a1a32bea520c592da69b4018982e662ae2a2513142509ae8e"


def test_expected_scope_counts_are_frozen():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_counts"] == {
        "short_horizon_groups": 9,
        "certifiable_winner_groups": 5,
        "unresolved_no_champion_groups": 4,
        "long_horizon_monte_carlo_routes": 6,
        "preserved_scorecard_rows": 90,
    }


def test_model_selection_cannot_reopen():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    scope = payload["certification_scope"]
    assert scope["reopen_model_selection"] is False
    assert scope["certify_only_existing_repaired_winners"] is True


def test_prediction_and_error_recomputation_prohibited():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    scope = payload["certification_scope"]
    assert scope["recompute_predictions"] is False
    assert scope["recompute_errors"] is False


def test_no_champion_groups_cannot_be_forced():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["certification_scope"]["force_resolution_of_no_champion_groups"] is False


def test_all_three_partitions_required():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["uncertainty_design"]["required_partitions"] == [
        "OUTER_ALL",
        "LATEST_TIME_STRESS",
        "PRODUCT_CONCENTRATION_STRESS",
    ]


def test_unavailable_bias_metric_cannot_be_fabricated():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    disposition = payload["uncertainty_design"]["unavailable_metric_disposition"]
    assert disposition["status"] == "NOT_EVALUABLE_FROM_PRESERVED_SCORECARD"
    assert disposition["fabrication_prohibited"] is True


def test_lower_uncertainty_is_conservatively_blocked():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "NO_WINNER_MAY_RECEIVE_LOWER_UNCERTAINTY" in payload["uncertainty_design"]["conservative_rule"]


def test_long_horizon_routes_require_monte_carlo():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    routing = payload["long_horizon_routing"]
    assert routing["required_simulations_per_product_horizon"] == 10000
    assert routing["required_horizon_days"] == [1095, 1825]
    assert routing["direct_winner_certification_authorized"] is False


def test_forecast_and_purchase_authority_remain_false():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["forecast_generation_authorized"] is False
    assert payload["purchase_analysis_authorized"] is False
    assert payload["purchase_recommendation_authorized"] is False


def test_module_loads():
    module = load_module()
    assert callable(module.main)
