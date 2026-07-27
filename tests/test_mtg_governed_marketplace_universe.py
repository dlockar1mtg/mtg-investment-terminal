from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_mtg_governed_marketplace_universe.py"
    spec = importlib.util.spec_from_file_location(
        "build_mtg_governed_marketplace_universe", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_governed_marketplace_universe_has_all_products():
    module = load_module()
    rows, summary = module.build_rows(module.DEFAULT_OVERRIDES)
    assert summary["status"] == "PASS"
    assert len(rows) == 1141
    assert summary["product_class_counts"] == {
        "COLLECTOR_BOOSTER_BOX": 49,
        "PRE_COLLECTOR_BOOSTER_BOX": 119,
        "SECRET_LAIR": 973,
    }


def test_secret_lairs_route_to_ebay_only():
    module = load_module()
    rows, _ = module.build_rows(module.DEFAULT_OVERRIDES)
    secret_lairs = [
        row for row in rows
        if row["product_class"] == "SECRET_LAIR"
    ]
    assert len(secret_lairs) == 973
    assert all(
        row["collection_lane"] == "EBAY_ONLY"
        for row in secret_lairs
    )
    assert all(row["ebay_query"] for row in secret_lairs)


def test_tcgplayer_products_route_to_tcgcsv():
    module = load_module()
    rows, summary = module.build_rows(module.DEFAULT_OVERRIDES)
    eligible = [
        row for row in rows
        if row["collection_lane"] == "EBAY_AND_TCGCSV"
    ]
    assert len(eligible) == summary["tcgcsv_eligible_products"]
    assert all(row["tcgplayer_product_id"] for row in eligible)


def test_manual_three_row_map_is_override_layer_not_universe():
    module = load_module()
    rows, summary = module.build_rows(module.DEFAULT_OVERRIDES)
    assert len(rows) == 1141
    assert summary["manual_override_count"] >= 3
