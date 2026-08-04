from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_winner_uncertainty_certification_execution.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_winner_uncertainty_certification_execution_contract_v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("winner_uncertainty_execution", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["contract_id"] == "precollector_winner_uncertainty_certification_execution_v1"


def test_contract_binds_certified_architecture_hash():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["required_architecture_package"]["sha256"] == "6f27cfe24f14be57faa9ccbf7f2bd766da0832c14c8db5cd49724d49cdead08d"


def test_contract_binds_repair_execution_hash():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["required_repair_execution_package"]["sha256"] == "fcdc8843f5c9ba0a1a32bea520c592da69b4018982e662ae2a2513142509ae8e"


def test_scope_counts_are_frozen():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["expected_counts"]["certifiable_winner_groups"] == 5
    assert payload["expected_counts"]["unresolved_no_champion_groups"] == 4
    assert payload["expected_counts"]["long_horizon_monte_carlo_routes"] == 6


def test_lower_uncertainty_is_prohibited():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["uncertainty_rules"]["lower_uncertainty_authorized"] is False


def test_missing_bias_metric_is_preserved():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["uncertainty_rules"]["mean_signed_percentage_error_status"] == "NOT_EVALUABLE_FROM_PRESERVED_SCORECARD"


def test_model_selection_and_recomputation_are_prohibited():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prohibited = payload["prohibited_behavior"]
    assert prohibited["reopen_model_selection"] is True
    assert prohibited["recompute_predictions"] is True
    assert prohibited["recompute_errors"] is True


def test_forecast_and_purchase_authority_remain_false():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["forecast_generation_authorized"] is False
    assert payload["purchase_analysis_authorized"] is False
    assert payload["purchase_recommendation_authorized"] is False


def test_next_stage_is_long_horizon_monte_carlo_architecture():
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["next_stage_if_certified"] == "PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_ARCHITECTURE"


def test_module_loads():
    module = load_module()
    assert callable(module.main)
