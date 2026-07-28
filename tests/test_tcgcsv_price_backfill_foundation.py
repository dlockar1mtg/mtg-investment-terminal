from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load(name: str, filename: str):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_map_builder_excludes_ambiguous_and_not_found():
    module = load("phase11e7_map", "build_tcgcsv_price_backfill_map.py")
    rows = [
        {
            "investment_product_id": "A",
            "canonical_product_name": "Confirmed",
            "finish_group": "FOIL",
            "product_group": "STANDARD_DROP",
            "tcgplayer_product_id": "1",
            "tcgcsv_group_id": "2576",
            "tcgcsv_product_name": "Confirmed",
            "discovery_status": "TCGCSV_ID_CONFIRMED",
        },
        {
            "investment_product_id": "B",
            "canonical_product_name": "Ambiguous",
            "finish_group": "FOIL",
            "product_group": "STANDARD_DROP",
            "tcgplayer_product_id": "2",
            "tcgcsv_group_id": "2576",
            "tcgcsv_product_name": "Ambiguous",
            "discovery_status": "TCGCSV_ID_AMBIGUOUS",
        },
        {
            "investment_product_id": "C",
            "canonical_product_name": "Missing",
            "finish_group": "FOIL",
            "product_group": "STANDARD_DROP",
            "tcgplayer_product_id": "",
            "tcgcsv_group_id": "",
            "tcgcsv_product_name": "",
            "discovery_status": "TCGCSV_ID_NOT_FOUND",
        },
    ]
    # Pad to contract size without creating more automatic rows.
    for index in range(970):
        rows.append({
            "investment_product_id": f"N{index}",
            "canonical_product_name": f"Missing {index}",
            "finish_group": "UNSPECIFIED",
            "product_group": "BUNDLE",
            "tcgplayer_product_id": "",
            "tcgcsv_group_id": "",
            "tcgcsv_product_name": "",
            "discovery_status": "TCGCSV_ID_NOT_FOUND",
        })
    maps, statuses, summary = module.build(rows)
    assert len(maps) == 1
    assert maps[0]["investment_product_id"] == "A"
    assert len(statuses) == 973
    assert statuses[1]["automatic_collection_allowed"] == "NO"


def test_current_collector_prefers_normal_subtype():
    module = load("phase11e7_current", "collect_confirmed_tcgcsv_current_prices.py")
    chosen = module.select_price([
        {"productId": 1, "subTypeName": "Foil", "marketPrice": 10},
        {"productId": 1, "subTypeName": "Normal", "marketPrice": 20},
    ])
    assert chosen["subTypeName"] == "Normal"


def test_current_collector_falls_back_to_first_subtype():
    module = load("phase11e7_current2", "collect_confirmed_tcgcsv_current_prices.py")
    chosen = module.select_price([
        {"productId": 1, "subTypeName": "Foil", "marketPrice": 10},
    ])
    assert chosen["marketPrice"] == 10
