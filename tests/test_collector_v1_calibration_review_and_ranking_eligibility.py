from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_calibration_review_and_ranking_eligibility_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_calibration_review_and_ranking_eligibility.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_uses_certified_calibration_outputs() -> None:
    for relative in load_contract()["authorities"].values():
        assert (ROOT / relative).is_file(), relative


def test_contract_preserves_rank_and_purchase_blocks() -> None:
    rules = load_contract()["eligibility_rules"]
    assert rules["structural_block_always_blocks"] is True
    assert rules["unresolved_primary_horizon_reasonableness_issue_blocks"] is True
    assert rules["unresolved_supporting_horizon_issue_allows_limited_candidate_only"] is True
    assert rules["at_least_one_short_or_primary_row_with_realized_validation_required"] is True
    assert rules["long_horizon_insufficient_realized_validation_alone_does_not_block"] is True
    assert rules["no_forecast_values_may_be_modified"] is True
    assert rules["ranking_authorized"] is False
    assert rules["purchase_recommendations_authorized"] is False


def test_candidate_statuses_are_explicit() -> None:
    assert load_contract()["candidate_statuses"] == [
        "RANKING_ELIGIBLE",
        "RANKING_ELIGIBLE_WITH_LIMITATIONS",
        "REASONABLENESS_REVIEW_REQUIRED",
        "INSUFFICIENT_FOR_RANKING",
        "BLOCKED",
    ]


def test_script_contains_required_outputs_and_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "collector_calibration_review_queue.csv",
        "collector_ranking_eligibility_candidate.csv",
        "collector_calibration_review_and_ranking_eligibility_summary.json",
        "UNRESOLVED_PRIMARY_HORIZON_ISSUE",
        "NO_SHORT_OR_PRIMARY_REALIZED_VALIDATION",
        "RANKING_ELIGIBLE_WITH_LIMITATIONS",
        '"ranking_authorized": False',
        '"purchase_recommendations_authorized": False',
        '"forecast_values_modified": False',
    ]:
        assert token in text


def test_script_contains_no_manual_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_contract_has_expected_scope() -> None:
    contract = load_contract()
    assert contract["required_products"] == 49
    assert contract["required_forecast_rows"] == 294
    assert contract["primary_ranking_horizons_days"] == [365, 1095]
    assert contract["expected_status"] == "PASS_COLLECTOR_CALIBRATION_REVIEW_AND_RANKING_ELIGIBILITY_CANDIDATE"
