from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_live_current_price_collection.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_live_current_price_collection_contract_v1.json"
SPEC = importlib.util.spec_from_file_location("precollector_live_current_price", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_preserves_downstream_blocks() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["controls"] == {
        "historical_append_authorized": False,
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
    }


def test_normalize_id() -> None:
    assert MODULE.normalize_id("tcgplayer:123") == "123"
    assert MODULE.normalize_id("123.0") == "123"


def test_build_product_map_rejects_missing_mapping() -> None:
    canonical = pd.DataFrame({
        "product_name": [f"Box {i}" for i in range(124)],
        "canonical_product_id": [f"tcgplayer:{i}" for i in range(124)],
        "governed_asset_key": [f"key-{i}" for i in range(124)],
    })
    source = pd.DataFrame({"productId": [str(i) for i in range(123)], "categoryId": [1] * 123, "groupId": [2] * 123})
    with pytest.raises(RuntimeError, match="PRODUCT_MAP_REQUIRED_FIELD_BLANK"):
        MODULE.build_product_map(canonical, source)


def test_classify_accepts_fresh_positive_normal_observation() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    product_map = pd.DataFrame({
        "box_name": ["A Box"],
        "tcgplayer_product_id": ["1"],
        "canonical_product_id": ["tcgplayer:1"],
        "governed_asset_key": ["a"],
        "tcgcsv_category_id": ["1"],
        "tcgcsv_group_id": ["2"],
        "source_product_name": ["A Box"],
    })
    observations = pd.DataFrame({
        "retrieval_id": ["r"],
        "box_name": ["A Box"],
        "tcgplayer_product_id": ["1"],
        "source_name": ["tcgcsv"],
        "source_timestamp": [pd.Timestamp.now(tz="UTC").isoformat()],
        "collected_at": [pd.Timestamp.now(tz="UTC").isoformat()],
        "price_selection_status": ["NORMAL_SUBTYPE_UNIQUE"],
        "admission_status": ["PRICE_CANDIDATE"],
        "market_price": [100.0],
        "price_data_quality": [100],
    })
    result = MODULE.classify(observations, product_map, contract)
    assert result.loc[0, "current_price_authority_status"] == "CURRENT_PRICE_AUTHORITY_CANDIDATE"
    assert result.loc[0, "blocking_reasons"] == ""


def test_classify_blocks_missing_market_price() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    product_map = pd.DataFrame({
        "box_name": ["A Box"], "tcgplayer_product_id": ["1"], "canonical_product_id": ["tcgplayer:1"],
        "governed_asset_key": ["a"], "tcgcsv_category_id": ["1"], "tcgcsv_group_id": ["2"], "source_product_name": ["A Box"],
    })
    observations = pd.DataFrame({
        "retrieval_id": ["r"], "box_name": ["A Box"], "tcgplayer_product_id": ["1"], "source_name": ["tcgcsv"],
        "source_timestamp": [pd.Timestamp.now(tz="UTC").isoformat()], "collected_at": [pd.Timestamp.now(tz="UTC").isoformat()],
        "price_selection_status": ["NORMAL_SUBTYPE_UNIQUE"], "admission_status": ["PRICE_CANDIDATE"],
        "market_price": [None], "price_data_quality": [50],
    })
    result = MODULE.classify(observations, product_map, contract)
    assert result.loc[0, "current_price_authority_status"] == "BLOCKED"
    assert "POSITIVE_MARKET_PRICE_REQUIRED" in result.loc[0, "blocking_reasons"]
