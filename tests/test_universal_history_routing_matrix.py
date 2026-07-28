from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_history_routing_matrix.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_history_routing_matrix",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unique_non_secret_lair_pair_is_archive_eligible():
    module = load_module()
    universe = [{
        "universal_mtg_product_id": "CB-1",
        "canonical_product_name": "Collector Box",
        "product_class": "COLLECTOR_BOOSTER_BOX",
        "product_group": "COLLECTOR",
        "finish_group": "",
        "tcgplayer_product_id": "123",
        "release_date": "2022-01-01",
    }]
    canonical = [{
        "tcgplayer_product_id": "123",
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "999",
    }]
    routes, groups, _ = module.build_routes(universe, [], canonical, [])
    assert routes[0]["tcgcsv_archive_eligible"] == "true"
    assert routes[0]["primary_history_route"] == "TCGCSV_MONTHLY_ARCHIVE"
    assert len(groups) == 1


def test_ambiguous_non_secret_lair_pair_is_not_automated():
    module = load_module()
    universe = [{
        "universal_mtg_product_id": "CB-1",
        "canonical_product_name": "Collector Box",
        "product_class": "COLLECTOR_BOOSTER_BOX",
        "tcgplayer_product_id": "123",
    }]
    canonical = [
        {
            "tcgplayer_product_id": "123",
            "tcgcsv_category_id": "1",
            "tcgcsv_group_id": "999",
        },
        {
            "tcgplayer_product_id": "123",
            "tcgcsv_category_id": "1",
            "tcgcsv_group_id": "1000",
        },
    ]
    routes, _, _ = module.build_routes(universe, [], canonical, [])
    assert routes[0]["tcgcsv_archive_eligible"] == "false"
    assert "AMBIGUOUS" in routes[0]["tcgcsv_identity_status"]


def test_secret_lair_confirmed_route_is_preserved():
    module = load_module()
    universe = [{
        "universal_mtg_product_id": "SL-1",
        "canonical_product_name": "Secret Lair",
        "product_class": "SECRET_LAIR",
        "tcgplayer_product_id": "456",
    }]
    sl_routes = [{
        "investment_product_id": "SL-1",
        "discovery_status": "TCGCSV_ID_CONFIRMED",
        "automatic_collection_allowed": "true",
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "2576",
    }]
    routes, groups, _ = module.build_routes(universe, sl_routes, [], [])
    assert routes[0]["tcgcsv_archive_eligible"] == "true"
    assert groups[0]["tcgcsv_group_id"] == "2576"

def test_secret_lair_matches_governed_source_product_id():
    module = load_module()
    universe = [{
        "universal_mtg_product_id": "UMTG-SL-0001",
        "source_product_id": "SL-1",
        "canonical_product_name": "Secret Lair",
        "product_class": "SECRET_LAIR",
        "tcgplayer_product_id": "",
    }]
    sl_routes = [{
        "investment_product_id": "SL-1",
        "discovery_status": "TCGCSV_ID_CONFIRMED",
        "automatic_collection_allowed": "true",
        "tcgplayer_product_id": "456",
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "2576",
    }]
    routes, groups, _ = module.build_routes(
        universe,
        sl_routes,
        [],
        [],
    )
    assert routes[0]["tcgplayer_product_id"] == "456"
    assert routes[0]["tcgcsv_archive_eligible"] == "true"
    assert routes[0]["history_reason_code"] == (
        "SECRET_LAIR_CONFIRMED_TCGCSV_IDENTITY"
    )
    assert groups[0]["tcgcsv_group_id"] == "2576"

