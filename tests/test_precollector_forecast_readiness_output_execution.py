from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_forecast_readiness_output_execution.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_forecast_readiness_output_execution_contract_v1.json"


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("forecast_output_execution", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_forecast_readiness_output_execution_v1"


def test_contract_binds_certified_packages():
    contract = payload()
    assert contract["required_architecture_package"]["sha256"] == "f1b35a30c6689612e8d319349e1a467e109724f25d03f747a59d2a55cf5e3ac4"
    assert contract["required_monte_carlo_execution_package"]["sha256"] == "5e0b70ab17a166a05521015c754789275a4d287c2458213f01248c48477cbc20"
    assert contract["required_winner_uncertainty_execution_package"]["sha256"] == "2a3385fe2f60ddda27e9d0f906cb3e87fea67945d9c0b2e79b5e3cb746837af0"


def test_expected_counts_are_frozen():
    assert payload()["expected_counts"] == {
        "governed_products": 50,
        "long_horizon_output_rows": 100,
        "short_horizon_certified_winners": 5,
        "short_horizon_unresolved_groups": 4,
        "short_horizon_scope_rows": 9,
    }


def test_no_recomputation_or_selection_reopening():
    scope = payload()["execution_scope"]
    assert scope["recompute_monte_carlo"] is False
    assert scope["reopen_model_selection"] is False
    assert scope["modify_certifications"] is False


def test_short_horizon_product_values_remain_blank():
    rules = payload()["output_rules"]
    assert rules["short_horizon_product_values_must_remain_blank"] is True
    assert rules["short_horizon_product_value_status"] == "NOT_MATERIALIZABLE_FROM_CERTIFIED_PACKAGE"


def test_ranking_and_purchase_authority_remain_false():
    contract = payload()
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_next_stage_is_ranking_readiness_architecture():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_RANKING_READINESS_ARCHITECTURE"


def test_module_loads():
    assert callable(load_module().main)
