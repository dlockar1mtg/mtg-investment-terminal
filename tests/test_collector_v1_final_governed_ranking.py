from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_governed_ranking_contract_v1.json"
SCRIPT = ROOT / "scripts/rank_collector_v1_final_governed_1_49.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_has_full_49_product_competition() -> None:
    contract = load_contract()
    assert contract["required_products"] == 49
    assert contract["required_forecast_rows"] == 294
    assert contract["primary_horizons_days"] == [365, 1095]
    rules = contract["rules"]
    assert rules["full_49_product_competition_required"] is True
    assert rules["primary_horizon_rows_required"] is True
    assert rules["cross_sectional_percentile_normalization_required"] is True
    assert rules["eligibility_penalties_must_be_applied"] is True
    assert rules["conditional_products_remain_purchase_ineligible"] is True
    assert rules["forecast_values_must_not_be_modified"] is True
    assert rules["ranking_authorized"] is True
    assert rules["purchase_recommendations_authorized"] is False


def test_weights_sum_to_one_and_preserve_governed_components() -> None:
    weights = load_contract()["weights"]
    assert abs(sum(float(value) for value in weights.values()) - 1.0) < 1e-9
    assert weights["forecast_return_365"] == 0.30
    assert weights["forecast_return_1095_annualized"] == 0.10
    assert weights["early_opportunity"] == 0.15
    assert weights["supply_demand"] == 0.10


def test_all_declared_authorities_exist() -> None:
    for relative in load_contract()["authorities"].values():
        assert (ROOT / relative).is_file(), relative


def test_script_has_required_fail_closed_controls_and_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "FINAL_RANKING_ELIGIBILITY_NOT_PASS",
        "RANKING_EXECUTION_NOT_AUTHORIZED",
        "PRIMARY_HORIZON_FORECAST_MISSING",
        "PRIMARY_HORIZON_VALUE_MISSING",
        "SCORABLE_PRODUCT_COUNT",
        "RANK_SEQUENCE_INVALID",
        "DUPLICATE_RANKED_PRODUCT",
        "FORECAST_VALUES_MODIFIED",
        "collector_final_governed_1_49_rankings.csv",
        "collector_final_ranking_factor_audit.csv",
        "collector_top_10_investment_candidates.csv",
        "collector_final_governed_ranking_summary.json",
    ]:
        assert token in text


def test_script_uses_deterministic_percentile_ranking_and_tie_breaker() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "def percentile" in text
    assert "canonical_product_id" in text
    assert "ranking_penalty_points" in text
    assert "final_governed_score" in text
    assert "(-float(row[\"final_governed_score\"]), row[\"canonical_product_id\"])" in text


def test_script_does_not_hardcode_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_purchase_authorization_remains_false() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"purchase_recommendations_authorized": False' in text
    assert '"ranking_authorized": True' in text
