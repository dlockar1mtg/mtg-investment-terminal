from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_end_to_end_governance_audit_v2_contract.json"
SCRIPT = ROOT / "scripts/audit_collector_v1_end_to_end_governance_v2.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_all_governed_stages_are_included() -> None:
    contract = load_contract()
    assert contract["required_stage_count"] == 11
    assert len(contract["stages"]) == 11
    names = {stage["stage"] for stage in contract["stages"]}
    assert "calibration_review_and_ranking_candidate" in names
    assert "purchase_recommendation_certification" in names


def test_correct_canonical_output_paths_are_bound() -> None:
    authorities = load_contract()["final_authorities"]
    assert authorities["forecast_lineage"].endswith("collector_final_forecast_source_identity_lineage_manifest.csv")
    assert authorities["blocked_horizons"].endswith("collector_final_authority_bound_blocked_horizons.csv")
    assert "coverage" not in authorities


def test_standard_matrix_uses_actual_canonical_clauses() -> None:
    requirements = load_contract()["standard_requirements"]
    assert len(requirements) == 11
    text = "\n".join(item["required_text"] for item in requirements)
    assert "Every governed product receives an explicit forecast method" in text
    assert "Forecast generation and purchase authorization remain separate" in text
    assert "Changes to methods, weights, thresholds" in text


def test_script_resolves_summaries_by_exact_status() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "locate_summary_by_status" in text
    assert "STAGE_SUMMARY_STATUS_RESOLUTION_FAILED" in text
    assert "declared_hashes" in text
    assert "hashes_to_paths" in text


def test_script_deduplicates_inventory_and_derives_coverage_from_summary() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'inventory: dict[str, dict[str, Any]]' in text
    assert 'final_counts["coverage_rows"]' in text
    assert "collector_complete_output_inventory.csv" in text


def test_read_only_safety_controls_are_present() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in [
        "CONDITIONAL_PRODUCTS_PURCHASE_AUTHORIZED",
        "FORECAST_VALUES_MODIFIED",
        "AUTOMATIC_PURCHASE_EXECUTION_NOT_FALSE",
        "SNAPSHOT_ID_INCONSISTENT",
    ]:
        assert token in text
