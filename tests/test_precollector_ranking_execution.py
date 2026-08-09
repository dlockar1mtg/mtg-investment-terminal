from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_ranking_execution.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_ranking_execution_contract_v1.json"


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("precollector_ranking_execution", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_ranking_execution_v1"


def test_contract_binds_architecture_hash():
    assert payload()["required_architecture_package"]["sha256"] == "8f0235e32674633ef7956d0c55c6de12948a2f51d966de5b01de6bd0b476a660"


def test_contract_binds_forecast_output_hash():
    assert payload()["required_forecast_output_execution_package"]["sha256"] == "27af2c4f566e87feaa51c2d75412522c8e8f939ae31192897e92a85f882791f8"


def test_expected_counts_are_frozen():
    assert payload()["expected_counts"] == {
        "governed_products": 50,
        "long_horizon_output_rows": 100,
        "ranked_product_rows": 50,
        "ranking_components": 6,
    }


def test_weights_sum_to_one():
    assert abs(sum(item["weight"] for item in payload()["ranking_policy"]["components"]) - 1.0) < 1e-12


def test_short_horizon_values_are_prohibited():
    assert payload()["execution_scope"]["use_short_horizon_product_values"] is False


def test_purchase_authority_remains_false():
    contract = payload()
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_next_stage_is_purchase_analysis_readiness():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_PURCHASE_ANALYSIS_READINESS_ARCHITECTURE"


def test_percentile_rewards_higher_values_when_higher_is_better():
    module = load_module()
    result = module.percentile(pd.Series([1.0, 2.0, 3.0]), True)
    assert result.iloc[2] > result.iloc[0]


def test_percentile_rewards_lower_values_when_lower_is_better():
    module = load_module()
    result = module.percentile(pd.Series([0.1, 0.2, 0.3]), False)
    assert result.iloc[0] > result.iloc[2]


def test_module_loads():
    assert callable(load_module().main)
