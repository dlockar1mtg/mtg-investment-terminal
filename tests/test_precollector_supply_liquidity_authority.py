from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_supply_liquidity_authority_contract_v1.json"
SCRIPT_PATH = ROOT / "scripts/build_precollector_supply_liquidity_authority.py"
GATE_PATH = ROOT / "scripts/run_precollector_supply_liquidity_authority_gate.ps1"


def load_module():
    spec = importlib.util.spec_from_file_location("precollector_supply_liquidity_authority", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_is_fail_closed_and_counts_are_bound():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["expected_model_input_candidate_count"] == 94
    assert contract["collector_supply_snapshot_expected_rows"] == 50
    assert contract["collector_accepted_listing_ledger_expected_rows"] == 562
    assert contract["next_stage_if_incomplete_candidate_coverage"] == "PRECOLLECTOR_LIVE_SUPPLY_COLLECTION"
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_builder_uses_certified_collector_sources_without_cross_lane_borrowing():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "collector_ebay_day_one_product_supply_snapshot.csv" in text
    assert "collector_ebay_day_one_accepted_listing_ledger.csv" in text
    assert "collector_supply_identity_match" in text
    assert "PRECOLLECTOR_SUPPLY_EVIDENCE_REQUIRED" in text
    assert "cross_lane_identity_borrowing_detected" in text
    assert "PRECOLLECTOR_LIVE_SUPPLY_COLLECTION" in text


def test_builder_preserves_governed_candidate_ceiling_and_downstream_blocks():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "MODEL_INPUT_CANDIDATE_COUNT_DRIFT" in text
    assert "SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE" in text
    assert 'review["forecast_authorized"] = False' in text
    assert 'review["ranking_authorized"] = False' in text
    assert 'review["purchase_recommendation_authorized"] = False' in text
    assert 'review["automatic_execution_authorized"] = False' in text


def test_builder_validates_source_schema_freshness_and_reconciliation():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "COLLECTOR_SUPPLY_SCHEMA_DRIFT" in text
    assert "COLLECTOR_SUPPLY_OBSERVATION_DATE_DRIFT" in text
    assert "FUTURE_SUPPLY_OBSERVATION_DATE" in text
    assert "DUPLICATE_COLLECTOR_SUPPLY_CANONICAL_PRODUCT_ID" in text


def test_gate_requires_targeted_and_full_regression_and_clean_completion():
    text = GATE_PATH.read_text(encoding="utf-8")
    assert "audit_precollector_scope_governance.py" in text
    assert "test_precollector_supply_liquidity_authority.py" in text
    assert "build_precollector_supply_liquidity_authority.py" in text
    assert "Full repository regression suite" in text
    assert "Assert-CleanTree" in text
    assert "CERTIFIED_PASS_PRECOLLECTOR_SUPPLY_LIQUIDITY_AUTHORITY_GATE" in text


def test_module_imports():
    module = load_module()
    assert callable(module.main)
    assert callable(module.sha256_file)
