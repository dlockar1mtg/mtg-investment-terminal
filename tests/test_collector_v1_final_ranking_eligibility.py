from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_final_ranking_eligibility_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_final_ranking_eligibility.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_preserves_full_competition_and_purchase_block() -> None:
    contract = load_contract()
    assert contract["required_products"] == 49
    assert contract["required_forecast_rows"] == 294
    rules = contract["rules"]
    assert rules["all_governed_products_enter_ranking_competition"] is True
    assert rules["limited_evidence_is_penalized_not_silently_excluded"] is True
    assert rules["supporting_horizon_issue_does_not_block_primary_horizon_ranking"] is True
    assert rules["primary_horizon_issue_requires_review"] is True
    assert rules["structural_failure_blocks_ranking"] is True
    assert rules["conditional_products_are_purchase_ineligible"] is True
    assert rules["forecast_values_must_not_be_modified"] is True
    assert rules["ranking_execution_authorized"] is True
    assert rules["purchase_recommendations_authorized"] is False


def test_contract_uses_existing_certified_authorities() -> None:
    for relative in load_contract()["authorities"].values():
        assert (ROOT / relative).is_file(), relative


def test_penalties_are_explicit_and_ordered() -> None:
    penalties = load_contract()["penalties"]
    assert penalties["ranking_eligible_with_limitations"] == 5.0
    assert penalties["supporting_horizon_review"] == 5.0
    assert penalties["conditional_no_realized_primary_validation"] == 15.0
    assert penalties["conditional_no_realized_primary_validation"] > penalties["ranking_eligible_with_limitations"]


def test_script_has_required_fail_closed_controls_and_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "UNRESOLVED_BLOCKING_RANKING_STATUS",
        "NOT_ALL_PRODUCTS_ENTER_RANKING_COMPETITION",
        "FORECAST_VALUES_MODIFIED",
        "RETAINED_AS_SUPPORTING_HORIZON_LIMITATION",
        "CONDITIONAL_RANKING_ELIGIBLE",
        "collector_supporting_horizon_review_resolution.csv",
        "collector_final_ranking_eligibility_authority.csv",
        "collector_final_ranking_eligibility_summary.json",
    ]:
        assert token in text


def test_script_contains_no_hardcoded_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_primary_and_supporting_horizons_are_explicit() -> None:
    contract = load_contract()
    assert contract["primary_horizons_days"] == [365, 1095]
    assert contract["supporting_horizons_days"] == [90, 180, 730, 1825]
