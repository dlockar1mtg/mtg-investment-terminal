from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_audit_contract_v1.json"
SCRIPT = ROOT / "scripts/audit_collector_v1_end_to_end_governance.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_covers_full_governed_chain() -> None:
    contract = load_contract()
    assert contract["required_final_counts"]["governed_products"] == 50
    assert contract["required_final_counts"]["forecast_products"] == 49
    assert contract["required_final_counts"]["forecast_rows"] == 294
    assert contract["required_final_counts"]["ranking_rows"] == 49
    assert contract["required_final_counts"]["purchase_rows"] == 49
    stages = {stage["stage"] for stage in contract["stages"]}
    for required in [
        "august1_current_data_package",
        "historical_observation_ledger",
        "final_premodel_resolution",
        "lorwyn_target_specific_comparables",
        "lorwyn_comparable_integration",
        "canonical_identity_lineage_recertification",
        "probabilistic_calibration",
        "final_ranking_eligibility",
        "final_governed_ranking",
        "purchase_recommendation_certification",
    ]:
        assert required in stages


def test_contract_requires_fail_closed_governance_controls() -> None:
    rules = load_contract()["rules"]
    for key in [
        "all_required_stages_must_pass",
        "all_required_outputs_must_exist",
        "all_json_must_parse",
        "all_csv_headers_must_be_unique",
        "critical_failures_must_be_empty",
        "authority_hashes_must_reconcile",
        "forecast_values_must_not_be_modified",
        "automatic_purchase_execution_must_remain_false",
        "conditional_products_must_not_be_purchase_authorized",
        "full_output_inventory_required",
        "human_review_required",
    ]:
        assert rules[key] is True


def test_final_authorities_are_explicit() -> None:
    authorities = load_contract()["final_authorities"]
    for key in [
        "current_price",
        "historical_ledger",
        "integrated_comparables",
        "final_forecasts",
        "forecast_lineage",
        "coverage",
        "calibration",
        "eligibility",
        "rankings",
        "purchase_authority",
    ]:
        assert key in authorities


def test_audit_engine_has_required_outputs_and_checks() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "STAGE_STATUS_MISMATCH",
        "STAGE_CRITICAL_FAILURES",
        "DUPLICATE_CSV_HEADERS",
        "JSON_PARSE_FAILED",
        "FINAL_AUTHORITY_MISSING",
        "FINAL_COUNT_MISMATCH",
        "CONDITIONAL_PRODUCTS_PURCHASE_AUTHORIZED",
        "AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE",
        "SNAPSHOT_ID_INCONSISTENT",
        "collector_complete_output_inventory.csv",
        "collector_stage_certification_audit.csv",
        "collector_authority_hash_reconciliation.csv",
        "collector_mtg_standard_control_matrix.csv",
        "collector_end_to_end_governance_audit_summary.json",
        "COLLECTOR_END_TO_END_GOVERNANCE_AUDIT_REPORT.md",
    ]:
        assert token in text


def test_audit_engine_does_not_modify_source_authorities() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "write_csv(OUTPUT /" in text
    assert "write_text(" in text
    assert "unlink(" not in text
    assert "replace(" not in text
    assert "shutil" not in text


def test_script_contains_no_hardcoded_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)


def test_expected_status_is_explicit() -> None:
    assert load_contract()["expected_status"] == (
        "PASS_COLLECTOR_END_TO_END_GOVERNANCE_AND_MTG_STANDARDS_AUDIT"
    )
