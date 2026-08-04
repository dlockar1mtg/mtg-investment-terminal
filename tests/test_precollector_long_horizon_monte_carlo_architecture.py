from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_long_horizon_monte_carlo_architecture.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_long_horizon_monte_carlo_architecture_contract_v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("long_horizon_monte_carlo_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_long_horizon_monte_carlo_architecture_v1"


def test_contract_binds_winner_uncertainty_execution_hash():
    assert payload()["required_winner_uncertainty_execution_package"]["sha256"] == "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"


def test_expected_long_horizon_counts_are_frozen():
    assert payload()["expected_counts"] == {
        "certified_short_horizon_winners": 5,
        "unresolved_short_horizon_groups": 4,
        "long_horizon_routes": 6,
        "long_horizon_horizon_codes": 2,
    }


def test_required_horizons_are_y3_and_y5():
    design = payload()["simulation_design"]
    assert design["horizon_codes"] == ["Y3", "Y5"]
    assert design["horizon_days"] == {"Y3": 1095, "Y5": 1825}


def test_simulation_count_is_10000_per_product_horizon():
    assert payload()["simulation_design"]["required_simulations_per_product_horizon"] == 10000


def test_distributional_outputs_and_quantiles_are_required():
    design = payload()["simulation_design"]
    assert design["required_quantiles"] == [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    assert "terminal_value_distribution" in design["required_outputs"]
    assert "probability_of_loss" in design["required_outputs"]


def test_seed_and_common_random_number_controls_are_required():
    design = payload()["simulation_design"]
    assert design["deterministic_seed_registry_required"] is True
    assert design["common_random_numbers_required_within_product"] is True


def test_all_uncertainty_layers_are_required():
    uncertainty = payload()["uncertainty_governance"]
    assert uncertainty["tail_stress_required"] is True
    assert uncertainty["parameter_uncertainty_required"] is True
    assert uncertainty["path_uncertainty_required"] is True
    assert uncertainty["scenario_uncertainty_required"] is True


def test_short_horizon_certifications_cannot_be_modified():
    governance = payload()["input_governance"]
    assert governance["reopen_short_horizon_model_selection"] is False
    assert payload()["prohibited_behavior"]["modify_short_horizon_certifications"] is True


def test_architecture_does_not_execute_simulations():
    assert payload()["prohibited_behavior"]["execute_monte_carlo"] is True


def test_forecast_ranking_and_purchase_authority_remain_false():
    contract = payload()
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_next_stage_is_monte_carlo_execution():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_LONG_HORIZON_MONTE_CARLO_EXECUTION"


def test_module_loads():
    assert callable(load_module().main)
