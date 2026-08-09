from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_long_horizon_monte_carlo_execution.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_long_horizon_monte_carlo_execution_contract_v1.json"


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("long_horizon_monte_carlo_execution", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_long_horizon_monte_carlo_execution_v1"


def test_contract_binds_certified_architecture_hash():
    assert payload()["required_architecture_package"]["sha256"] == "f77b965bc7acfe315050940e450a4ce011f194656556de06321249e551bcafc1"


def test_contract_binds_winner_execution_hash():
    assert payload()["required_winner_uncertainty_execution_package"]["sha256"] == "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"


def test_expected_product_horizon_scope_is_frozen():
    assert payload()["expected_counts"] == {
        "governed_products": 50,
        "long_horizon_routes": 6,
        "long_horizon_horizon_codes": 2,
        "product_horizon_rows": 100,
        "certified_short_horizon_winners": 5,
        "unresolved_short_horizon_groups": 4,
    }


def test_simulation_count_is_10000():
    assert payload()["simulation_policy"]["required_simulations_per_product_horizon"] == 10000


def test_horizons_are_y3_and_y5():
    assert payload()["simulation_policy"]["horizon_years"] == {"Y3": 3.0, "Y5": 5.0}


def test_required_quantiles_are_frozen():
    assert payload()["simulation_policy"]["required_quantiles"] == [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]


def test_deterministic_seed_is_stable_and_bounded():
    module = load_module()
    first = module.stable_seed("snapshot", "123", "Y3")
    second = module.stable_seed("snapshot", "123", "Y3")
    assert first == second
    assert 1 <= first <= 2147483647


def test_sparse_history_fallback_order_is_governed():
    assert payload()["simulation_policy"]["fallback_order"] == ["PRODUCT", "FORECAST_ROUTE_POOL", "GLOBAL_POOL"]


def test_all_uncertainty_layers_are_enabled():
    policy = payload()["simulation_policy"]
    assert policy["parameter_uncertainty"]["enabled"] is True
    assert policy["path_uncertainty"]["enabled"] is True
    assert policy["scenario_uncertainty"]["enabled"] is True
    assert policy["tail_stress"]["enabled"] is True


def test_snapshot_authorities_are_required():
    governance = payload()["input_governance"]
    assert governance["required_manifest_roles"] == ["canonical_history", "current_authority"]
    assert governance["new_live_collection_authorized"] is False


def test_short_horizon_certifications_cannot_change():
    governance = payload()["input_governance"]
    assert governance["modify_short_horizon_certifications"] is False
    assert governance["reopen_short_horizon_model_selection"] is False


def test_forecast_ranking_and_purchase_authority_remain_false():
    contract = payload()
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_next_stage_is_forecast_readiness_architecture():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_ARCHITECTURE"


def test_module_loads():
    assert callable(load_module().main)
