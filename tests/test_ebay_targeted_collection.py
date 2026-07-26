from __future__ import annotations

from pathlib import Path

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_targeted_collection import select_target_products


def _product(product_id: str, name: str) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id=f"canonical-{product_id}",
        canonical_product_name=name,
        canonical_set_name=name,
        product_class="COLLECTOR_BOOSTER_BOX",
        tcgplayer_product_id=product_id,
        release_date="2022-01-01",
        ebay_query=name,
    )


def test_product_map_targets_exact_tcgplayer_ids_in_map_order(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text(
        "box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\n"
        "Final Fantasy,618893,1,24219\n"
        "Double Masters 2022,271509,1,3070\n",
        encoding="utf-8",
    )
    universe = [
        _product("27257", "10th Edition Booster Box"),
        _product("271509", "Double Masters 2022 Collector Booster Display"),
        _product("618893", "Final Fantasy Collector Booster Display"),
    ]

    selected, missing = select_target_products(product_map, universe)

    assert [product.tcgplayer_product_id for product in selected] == ["618893", "271509"]
    assert missing == []


def test_missing_universe_product_is_constructed_from_governed_map(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text(
        "box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id,scryfall_set_code,source_product_name\n"
        "Final Fantasy Collector Booster Box,618893,1,24219,fin,Final Fantasy Collector Booster Display\n",
        encoding="utf-8",
    )

    selected, missing = select_target_products(product_map, [_product("1", "Other")])

    assert missing == []
    assert len(selected) == 1
    assert selected[0].tcgplayer_product_id == "618893"
    assert selected[0].canonical_product_id == "TCGPLAYER-618893"
    assert selected[0].canonical_product_name == "Final Fantasy Collector Booster Display"
    assert selected[0].product_class == "COLLECTOR_BOOSTER_BOX"


def test_invalid_map_target_without_name_is_reported(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text(
        "box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\n"
        ",999999,1,1\n",
        encoding="utf-8",
    )

    selected, missing = select_target_products(product_map, [_product("1", "Other")])

    assert selected == []
    assert missing == ["999999"]
