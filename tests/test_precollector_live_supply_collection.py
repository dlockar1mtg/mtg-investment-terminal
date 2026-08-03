from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_live_supply_collection_contract_v1.json"
SCRIPT_PATH = ROOT / "scripts/build_precollector_live_supply_collection.py"
GATE_PATH = ROOT / "scripts/run_precollector_live_supply_collection_gate.ps1"


def load_module():
    spec = importlib.util.spec_from_file_location("precollector_live_supply_collection", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_targets_certified_candidate_ceiling_and_is_fail_closed():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["expected_model_input_candidate_count"] == 94
    assert contract["limit_per_product"] == 200
    assert contract["next_stage_if_collection_passes"] == "PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY"
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_builder_runs_governed_targeted_ebay_collection():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "build_precollector_historical_price_authority_review.py" in text
    assert "run_daily_ebay_collection.py" in text
    assert "--product-map" in text
    assert "--dry-run" in text
    assert "MODEL_INPUT_CANDIDATE_COUNT_DRIFT" in text
    assert "TARGET_PRODUCT_MAP_RECONCILIATION_FAILED" in text
    assert "PRECOLLECTOR_EBAY_LIVE_COLLECTION_FAILED" in text
    assert "cross_lane_identity_borrowing_detected" in text


def test_gate_requires_clean_governed_completion():
    text = GATE_PATH.read_text(encoding="utf-8")
    assert "audit_precollector_scope_governance.py" in text
    assert "test_precollector_live_supply_collection.py" in text
    assert "build_precollector_live_supply_collection.py" in text
    assert "Full repository regression suite" in text
    assert "Assert-CleanTree" in text
    assert "Remove-Item $GeneratedArtifacts -Recurse -Force" in text
    assert "CERTIFIED_PASS_PRECOLLECTOR_LIVE_SUPPLY_COLLECTION_GATE" in text


def test_module_imports():
    module = load_module()
    assert callable(module.main)
    assert callable(module.sha256_file)
