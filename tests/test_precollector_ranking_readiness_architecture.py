from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_ranking_readiness_architecture.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_ranking_readiness_architecture_contract_v1.json"


def payload():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("ranking_readiness_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_parseable():
    assert payload()["contract_id"] == "precollector_ranking_readiness_architecture_v1"


def test_contract_binds_forecast_output_execution_hash():
    assert payload()["required_forecast_output_execution_package"]["sha256"] == "27af2c4f566e87feaa51c2d75412522c8e8f939ae31192897e92a85f882791f8"


def test_expected_scope_is_frozen():
    assert payload()["expected_counts"] == {
        "governed_products": 50,
        "long_horizon_output_rows": 100,
        "long_horizon_horizon_codes": 2,
        "short_horizon_scope_rows": 9,
    }


def test_ranking_is_long_horizon_only():
    scope = payload()["ranking_scope"]
    assert scope["eligible_horizons"] == ["Y3", "Y5"]
    assert scope["short_horizon_values_may_affect_rank"] is False


def test_ranking_weights_sum_to_one():
    components = payload()["ranking_policy"]["components"]
    assert abs(sum(float(item["weight"]) for item in components) - 1.0) < 1e-12


def test_ranking_has_return_downside_and_loss_components():
    names = {item["component"] for item in payload()["ranking_policy"]["components"]}
    assert {"Y3_MEDIAN_ANNUALIZED_RETURN", "Y5_MEDIAN_ANNUALIZED_RETURN"}.issubset(names)
    assert {"Y3_Q10_TERMINAL_MULTIPLE", "Y5_Q10_TERMINAL_MULTIPLE"}.issubset(names)
    assert {"Y3_PROBABILITY_OF_LOSS", "Y5_PROBABILITY_OF_LOSS"}.issubset(names)


def test_eligibility_requires_complete_distributional_evidence():
    policy = payload()["eligibility_policy"]
    assert policy["require_both_y3_and_y5"] is True
    assert policy["require_complete_quantiles"] is True
    assert policy["require_probability_fields"] is True
    assert policy["require_seed_and_lineage"] is True


def test_architecture_does_not_execute_rankings():
    assert payload()["ranking_scope"]["execute_rankings"] is False
    assert payload()["ranking_execution_authorized"] is False


def test_purchase_authority_remains_false():
    contract = payload()
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_next_stage_is_ranking_execution():
    assert payload()["next_stage_if_certified"] == "PRECOLLECTOR_RANKING_EXECUTION"


def test_module_loads():
    assert callable(load_module().main)
