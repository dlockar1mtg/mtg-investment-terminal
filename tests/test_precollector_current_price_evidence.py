from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_current_price_evidence.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_current_price_evidence_contract_v1.json"

SPEC = importlib.util.spec_from_file_location("precollector_current_price_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_preserves_downstream_blocks() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["historical_append_authorized"] is False
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_normalize_id_accepts_canonical_and_numeric_forms() -> None:
    assert MODULE.normalize_id("tcgplayer:123") == "123"
    assert MODULE.normalize_id("123.0") == "123"
    assert MODULE.normalize_id(123) == "123"


def test_first_column_is_case_insensitive() -> None:
    frame = pd.DataFrame(columns=["ProductId", "MarketPrice"])
    assert MODULE.first_column(frame, ["productId"]) == "ProductId"
    assert MODULE.first_column(frame, ["marketPrice"]) == "MarketPrice"


def test_contract_binds_certified_universe_hash() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["canonical_universe_sha256"] == "db5eee09b3fa4d02766734aab6c5f65d324bb49c77744f82ecd95f6f7ea7395e"


def test_source_snapshot_is_august_1_certified_snapshot() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "20260801T211201Z" in contract["source_snapshot"]


def test_price_field_policy_requires_positive_evidence() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["candidate_rule"]["identity_match_required"] is True
    assert contract["candidate_rule"]["positive_price_required"] is True
