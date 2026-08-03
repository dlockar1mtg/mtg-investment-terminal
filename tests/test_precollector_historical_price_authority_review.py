from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_historical_price_authority_review_contract_v1.json"
SCRIPT_PATH = ROOT / "scripts/build_precollector_historical_price_authority_review.py"
GATE_PATH = ROOT / "scripts/run_precollector_historical_price_authority_review_gate.ps1"


def load_module():
    spec = importlib.util.spec_from_file_location("precollector_historical_authority_review", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_exists_and_is_fail_closed():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["expected_canonical_historical_rows"] == 2826
    assert contract["minimum_history_rows"] >= 2
    assert contract["minimum_distinct_dates"] >= 2
    assert contract["next_stage_if_certified"] == "PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY"
    assert contract["historical_append_authorized"] is False
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_builder_declares_governed_inputs_and_outputs():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "build_precollector_canonical_historical_prices.py" in text
    assert "build_precollector_current_price_authority_review.py" in text
    assert "precollector_canonical_product_universe_v1.csv" in text
    assert "precollector_canonical_historical_prices_v1.csv" in text
    assert "precollector_current_price_authority_v1.csv" in text
    assert "precollector_current_price_blocked_products_v1.csv" in text
    assert "MODEL_INPUT_CANDIDATE" in text
    assert "CURRENT_AND_HISTORY_AUTHORIZED" in text
    assert "CURRENT_ONLY" in text
    assert "HISTORY_ONLY" in text
    assert "NEITHER_AUTHORIZED" in text


def test_builder_rejects_future_and_duplicate_history():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "FUTURE_HISTORICAL_ROWS" in text
    assert "DUPLICATE_CANONICAL_PRODUCT_TIMESTAMP" in text
    assert "INVALID_CANONICAL_HISTORY_ROWS" in text


def test_builder_preserves_downstream_restrictions():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'eligibility["forecast_authorized"] = False' in text
    assert 'eligibility["ranking_authorized"] = False' in text
    assert 'eligibility["purchase_recommendation_authorized"] = False' in text
    assert 'eligibility["automatic_execution_authorized"] = False' in text


def test_gate_exists_and_requires_clean_completion():
    text = GATE_PATH.read_text(encoding="utf-8")
    assert "audit_precollector_scope_governance.py" in text
    assert "test_precollector_historical_price_authority_review.py" in text
    assert "build_precollector_historical_price_authority_review.py" in text
    assert "Full repository regression suite" in text
    assert "Assert-CleanTree" in text
    assert "CERTIFIED_PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_REVIEW_GATE" in text
    assert "AUTHORIZED_NEXT_STAGE=PRECOLLECTOR_SUPPLY_AND_LIQUIDITY_AUTHORITY" in text


def test_module_imports():
    module = load_module()
    assert callable(module.main)
    assert callable(module.sha256_file)
