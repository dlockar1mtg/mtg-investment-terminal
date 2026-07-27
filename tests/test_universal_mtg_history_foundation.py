from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_mtg_history_foundation.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_mtg_history_foundation", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample_universe():
    return [
        {
            "canonical_product_id": "A",
            "box_name": "Product A",
            "product_class": "SECRET_LAIR",
            "tcgplayer_product_id": "",
            "collection_lane": "EBAY_ONLY",
            "ebay_query": "Product A sealed",
        },
        {
            "canonical_product_id": "B",
            "box_name": "Product B",
            "product_class": "COLLECTOR_BOOSTER_BOX",
            "tcgplayer_product_id": "123",
            "collection_lane": "EBAY_AND_TCGCSV",
            "ebay_query": "Product B sealed",
        },
    ]


def test_resolve_product_uses_all_identity_paths():
    module = load_module()
    universe = sample_universe()
    indexes = module.build_indexes(universe)

    product, method = module.resolve_product(
        {"canonical_product_id": "A"}, *indexes
    )
    assert product["canonical_product_id"] == "A"
    assert method == "CANONICAL_ID"

    product, method = module.resolve_product(
        {"tcgplayer_product_id": "123"}, *indexes
    )
    assert product["canonical_product_id"] == "B"
    assert method == "TCGPLAYER_ID"

    product, method = module.resolve_product(
        {"product_name": "Product A"}, *indexes
    )
    assert product["canonical_product_id"] == "A"
    assert method == "NORMALIZED_NAME"


def test_coverage_contains_every_governed_product():
    module = load_module()
    universe = sample_universe()
    history = [{
        "canonical_product_id": "B",
        "observation_date": "2026-01-01",
        "source_name": "TCGCSV",
        "price_field": "market_price",
        "is_live_observation": "true",
    }]
    coverage = module.build_coverage(universe, history)
    assert len(coverage) == 2
    by_id = {row["canonical_product_id"]: row for row in coverage}
    assert by_id["A"]["history_coverage_status"] == "NO_HISTORY_FOUND"
    assert by_id["B"]["history_coverage_status"] == "DIRECT_HISTORY_SINGLE"
    assert by_id["B"]["live_observation_count"] == 1


def test_full_model_contract_requires_every_product():
    module = load_module()
    coverage = module.build_coverage(sample_universe(), [])
    contract = module.build_model_contract(coverage)
    assert len(contract) == 2
    assert all(
        row["required_model_status"] == "FULL_MODEL_REQUIRED"
        for row in contract
    )
    assert all(row["live_collection_required"] == "true" for row in contract)


def test_identity_registry_includes_ebay_for_every_product():
    module = load_module()
    identity = module.build_identity(sample_universe())
    ebay = [row for row in identity if row["source_name"] == "EBAY"]
    assert len(ebay) == 2
    assert all(row["identity_status"] == "GOVERNED" for row in ebay)
