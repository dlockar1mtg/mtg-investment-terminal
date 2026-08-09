from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_historical_price_evidence_inventory.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_historical_price_evidence_inventory_contract_v1.json"
SPEC = importlib.util.spec_from_file_location("precollector_history_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_is_fail_closed() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["historical_append_authorized"] is False
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_normalize_id() -> None:
    assert MODULE.normalize_id("tcgplayer:123") == "123"
    assert MODULE.normalize_id("123.0") == "123"
    assert MODULE.normalize_id(None) == ""


def test_first_column_case_insensitive() -> None:
    assert MODULE.first_column(["ProductId", "Observed_At"], ["productId"]) == "ProductId"
    assert MODULE.first_column(["x"], ["date"]) is None


def test_inspect_csv_accepts_valid_history(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    pd.DataFrame({
        "tcgplayer_product_id": ["1", "1", "2"],
        "observation_date": ["2026-01-01", "2026-02-01", "2026-01-15"],
        "market_price": [10.0, 12.0, 0.0],
    }).to_csv(path, index=False)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    original_root = MODULE.ROOT
    MODULE.ROOT = tmp_path
    try:
        inventory, coverage = MODULE.inspect_csv(path, {"1", "2"}, contract)
    finally:
        MODULE.ROOT = original_root
    assert inventory["candidate_status"] == "HISTORICAL_EVIDENCE_CANDIDATE"
    assert inventory["canonical_overlap_products"] == 2
    assert inventory["positive_price_rows"] == 2
    assert len(coverage) == 1


def test_inspect_csv_blocks_missing_date(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    pd.DataFrame({"tcgplayer_product_id": ["1", "1"], "market_price": [10, 11]}).to_csv(path, index=False)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    original_root = MODULE.ROOT
    MODULE.ROOT = tmp_path
    try:
        inventory, _ = MODULE.inspect_csv(path, {"1"}, contract)
    finally:
        MODULE.ROOT = original_root
    assert inventory["candidate_status"] == "NOT_CANDIDATE"
    assert "DATE_COLUMN_MISSING" in inventory["blocking_reasons"]
