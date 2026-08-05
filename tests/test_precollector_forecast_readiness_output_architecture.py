from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_forecast_readiness_output_architecture.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_forecast_readiness_output_architecture_contract_v1.json"


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("forecast_readiness_output_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_forecast_readiness_output_architecture_v1"


def test_contract_binds_monte_carlo_execution_hash():
    assert payload()["required_monte_carlo_execution_package"]["sha256"] == "5e0b70ab17a166a05521015c754789275a4d287c2458213f01248c48477cbc20"


def test_contract_binds_winner_execution_hash():
    assert payload()["required_winner_uncertainty_execution_package"]["sha256"] == "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"


def test_expected_scope_is_frozen():
    assert payload()["expected_counts"] == {
        "governed_products": 50,
        "short_horizon_certified_winners": 5,
        "short_horizon_unresolved_groups": 4,
        "long_horizon_product_horizon_rows": 100,
        "long_horizon_horizon_codes": 2,
    }


def test_all_required_horizons_are_present():
    assert payload()["output_governance"]["required_horizons"] == ["D90", "D180", "D365", "Y3", "Y5"]


def test_long_horizon_distribution_fields_are_required():
    fields = set(payload()["output_governance"]["long_horizon_required_fields"])
    assert {"terminal_value_q05", "terminal_value_q50", "terminal_value_q95", "probability_of_loss", "seed"}.issubset(fields)


def test_uncertainty_and_lineage_disclosure_are_required():
    governance = payload()["output_governance"]
    assert governance["uncertainty_disclosure_required"] is True
    assert governance["lineage_disclosure_required"] is True
    assert governance["point_forecast_only_prohibited"] is True


def test_unresolved_short_horizon_values_must_remain_blank():
    assert payload()["output_governance"]["unresolved_short_horizon_output_must_remain_blank"] is True


def test_architecture_does_not_generate_or_recompute_forecasts():
    scope = payload()["readiness_scope"]
    assert scope["generate_new_forecasts"] is False
    assert scope["recompute_monte_carlo"] is False


def test_short_horizon_model_selection_cannot_reopen():
    scope = payload()["readiness_scope"]
    assert scope["reopen_short_horizon_model_selection"] is False
    assert scope["modify_short_horizon_certifications"] is False


def test_ranking_and_purchase_authority_remain_false():
    contract = payload()
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_next_stage_is_output_execution():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_FORECAST_READINESS_AND_OUTPUT_EXECUTION"


def test_module_loads():
    assert callable(load_module().main)
