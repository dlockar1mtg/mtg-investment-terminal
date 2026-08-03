from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_audit_closure_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_end_to_end_governance_audit_closure.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_binds_exact_snapshot_and_source_bundle() -> None:
    contract = load_contract()
    assert contract["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert contract["source_bundle_sha256"] == "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"


def test_contract_requires_exact_v2_failure_set() -> None:
    contract = load_contract()
    assert contract["required_v2_critical_failure"] == (
        "STAGE_SUMMARY_STATUS_RESOLUTION_FAILED:august1_current_data_package:0"
    )
    assert contract["required_v2_counts"]["stages_audited"] == 11
    assert contract["required_v2_counts"]["stages_passed"] == 10
    assert contract["required_v2_counts"]["declared_hashes_checked"] == 21
    assert contract["required_v2_counts"]["declared_hashes_reconciled_to_audited_inventory"] == 21
    assert contract["required_v2_counts"]["standard_requirements_documented"] == 11


def test_contract_preserves_all_final_authority_counts() -> None:
    counts = load_contract()["required_final_authority_counts"]
    assert counts == {
        "current_price": 50,
        "historical_ledger": 1215,
        "integrated_comparables": 121,
        "final_forecasts": 294,
        "forecast_lineage": 294,
        "blocked_horizons": 6,
        "calibration": 294,
        "eligibility": 49,
        "rankings": 49,
        "purchase_authority": 49,
        "coverage_rows": 300,
    }


def test_closure_requires_positive_certification_evidence_and_no_failures() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "AUGUST1_SNAPSHOT_EVIDENCE_NOT_FOUND",
        "AUGUST1_MODEL_INPUT_CERTIFICATION_NOT_FOUND",
        "AUGUST1_MODEL_REBUILD_AUTHORIZATION_NOT_FOUND",
        "AUGUST1_SOURCE_BUNDLE_HASH_NOT_FOUND",
        "AUGUST1_EXPLICIT_FAILURE_EVIDENCE",
        "AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE",
        "collector_august1_certification_evidence.json",
        "collector_end_to_end_governance_audit_closure_summary.json",
    ]:
        assert token in text


def test_closure_is_read_only_for_prior_authorities() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert ".write_text(" in text
    assert "OUTPUT /" in text
    assert "unlink(" not in text
    assert "replace(" not in text
    assert "shutil" not in text


def test_script_contains_no_product_specific_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)
