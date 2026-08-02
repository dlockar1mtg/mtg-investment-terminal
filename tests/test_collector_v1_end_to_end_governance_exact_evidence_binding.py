from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_exact_evidence_binding_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_end_to_end_governance_exact_evidence_binding.py"


def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_contract_binds_only_exact_discovered_evidence_files() -> None:
    paths = contract()["evidence_files"]
    assert paths == [
        "data/governance/permanence/certification/collector_v1_august_1_snapshot_registration/collector_v1_august_1_snapshot_registration_summary.json",
        "data/governance/permanence/certification/collector_v1_snapshot_bound_authority_verification/collector_v1_snapshot_bound_authority_verification_summary.json",
    ]
    for relative in paths:
        assert (ROOT / relative).is_file(), relative


def test_contract_preserves_snapshot_and_source_hash() -> None:
    cfg = contract()
    assert cfg["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert cfg["source_bundle_sha256"] == "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"


def test_contract_preserves_v2_counts_and_final_authorities() -> None:
    cfg = contract()
    assert cfg["required_v2_counts"]["declared_hashes_checked"] == 21
    assert cfg["required_v2_counts"]["declared_hashes_reconciled_to_audited_inventory"] == 21
    assert cfg["required_v2_counts"]["standard_requirements_documented"] == 11
    assert cfg["required_final_authority_counts"]["final_forecasts"] == 294
    assert cfg["required_final_authority_counts"]["forecast_lineage"] == 294
    assert cfg["required_final_authority_counts"]["coverage_rows"] == 300
    assert cfg["required_final_authority_counts"]["purchase_authority"] == 49


def test_script_checks_structured_failures_not_raw_failure_words() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "def structured_failures" in text
    assert "explicit_failure_term_match" not in text
    assert 'key_lower == "critical_failures"' in text
    assert "startswith(\"FAIL\")" in text


def test_script_is_fail_closed_and_writes_audit_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "EXACT_EVIDENCE_FILE_MISSING",
        "EXACT_SNAPSHOT_EVIDENCE_NOT_FOUND",
        "EXACT_SOURCE_HASH_EVIDENCE_NOT_FOUND",
        "EXACT_MODEL_INPUT_CERTIFICATION_NOT_FOUND",
        "EXACT_MODEL_REBUILD_AUTHORIZATION_NOT_FOUND",
        "EXACT_EVIDENCE_STRUCTURED_FAILURES",
        "collector_exact_august1_evidence_audit.json",
        "collector_end_to_end_governance_exact_evidence_binding_summary.json",
    ]:
        assert token in text


def test_script_does_not_hardcode_product_identity() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(value.startswith("MTG-CANON-TCGPLAYER-") for value in strings)
