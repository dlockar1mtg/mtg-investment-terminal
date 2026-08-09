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


def test_contract_is_bound_to_fresh_200_result_collection_and_fail_closed():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["expected_model_input_candidate_count"] == 94
    assert contract["expected_live_collection_product_count"] == 94
    assert contract["expected_live_listing_rows"] == 7488
    assert contract["expected_live_accepted_rows"] == 936
    assert contract["minimum_accepted_listing_count"] == 5
    assert contract["minimum_accepted_seller_count"] == 3
    assert contract["required_coverage_state"] == "STRONG_MATCH_COVERAGE"
    assert contract["next_stage_if_any_candidate_authorized"] == "PRECOLLECTOR_COMPARABLE_PRODUCT_TAXONOMY"
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_builder_uses_fresh_precollector_sources_without_cross_lane_borrowing():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ebay_product_coverage_2026-08-03.csv" in CONTRACT_PATH.read_text(encoding="utf-8")
    assert "ebay_listing_match_results_2026-08-03.csv" in CONTRACT_PATH.read_text(encoding="utf-8")
    assert "live_supply_identity_match" in text
    assert "PRECOLLECTOR_LIVE_SUPPLY_EVIDENCE_REQUIRED" in text
    assert "cross_lane_identity_borrowing_detected" in text
    assert "collector_ebay_day_one" not in text


def test_builder_preserves_candidate_ceiling_and_downstream_blocks():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "MODEL_INPUT_CANDIDATE_COUNT_DRIFT" in text
    assert "SUPPLY_ADJUSTED_MODEL_INPUT_CANDIDATE" in text
    assert 'review["forecast_authorized"] = False' in text
    assert 'review["ranking_authorized"] = False' in text
    assert 'review["purchase_recommendation_authorized"] = False' in text
    assert 'review["automatic_execution_authorized"] = False' in text


def test_builder_validates_fresh_source_schema_and_reconciliation():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "LIVE_SUPPLY_SCHEMA_DRIFT" in text
    assert "LIVE_SUPPLY_OBSERVATION_DATE_DRIFT" in text
    assert "LIVE_COLLECTION_ABORTED_EARLY" in text
    assert "LIVE_COLLECTION_MISSING_PRODUCT_IDS" in text
    assert "LIVE_MATCHER_NOT_FAIL_CLOSED" in text
    assert "DUPLICATE_LIVE_COVERAGE_TCGPLAYER_PRODUCT_ID" in text


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
