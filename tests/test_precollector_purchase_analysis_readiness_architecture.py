from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_purchase_analysis_readiness_architecture.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_purchase_analysis_readiness_architecture_contract_v1.json"


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("purchase_analysis_readiness_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_purchase_analysis_readiness_architecture_v1"


def test_contract_binds_certified_ranking_hash():
    assert payload()["required_ranking_execution_package"]["sha256"] == "2760613b72389bb0c4edc8c0ca737cc75988df24f7b50830d127c5f2c5b72791"


def test_expected_ranking_scope_is_frozen():
    assert payload()["expected_counts"] == {
        "governed_products": 50,
        "ranked_product_rows": 50,
        "ranking_components": 6,
    }


def test_required_dimensions_are_explicit():
    dimensions = payload()["required_purchase_analysis_dimensions"]
    assert len(dimensions) == 8
    assert "LIQUIDITY_AND_SUPPLY" in dimensions
    assert "BUDGET_FIT" in dimensions
    assert "POSITION_CONCENTRATION" in dimensions


def test_ranking_is_not_sufficient_for_purchase_analysis():
    assert payload()["readiness_policy"]["ranking_is_necessary_but_not_sufficient"] is True


def test_user_constraints_are_required():
    policy = payload()["readiness_policy"]
    assert policy["user_budget_required_before_purchase_analysis"] is True
    assert policy["existing_holdings_required_before_concentration_analysis"] is True


def test_short_horizon_values_cannot_be_imputed():
    policy = payload()["readiness_policy"]
    assert policy["short_horizon_product_values_available"] is False
    assert policy["short_horizon_values_may_not_be_imputed"] is True


def test_architecture_does_not_execute_or_recommend():
    scope = payload()["architecture_scope"]
    assert scope["execute_purchase_analysis"] is False
    assert scope["generate_purchase_recommendations"] is False
    assert scope["execute_purchases"] is False


def test_next_stage_is_input_certification():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_PURCHASE_ANALYSIS_INPUT_CERTIFICATION"


def test_purchase_authorities_remain_false():
    contract = payload()
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_module_loads():
    assert callable(load_module().main)
