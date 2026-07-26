from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_full_marketplace_product_map import build_full_product_map
from scripts.run_full_marketplace_universe import _batch_ranges
from scripts.run_mtg_marketplace_production import _split_collection_maps


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_governed_map_combines_boosters_and_secret_lairs(tmp_path: Path) -> None:
    products = tmp_path / "investment_products.csv"
    secret_lairs = tmp_path / "secret_lairs.csv"
    review = tmp_path / "review.csv"
    _write(products, [
        {
            "investment_product_id": "IP-1", "box_name": "Collector Box",
            "approved_product_name": "Collector Box", "approved_tcgplayer_product_id": "100",
            "tcgcsv_category_id": "1", "tcgcsv_group_id": "10",
            "investment_product_type": "Collector Booster Display", "approval_status": "approved", "notes": "",
        },
        {
            "investment_product_id": "IP-2", "box_name": "Ignored Bundle",
            "approved_product_name": "Ignored Bundle", "approved_tcgplayer_product_id": "101",
            "tcgcsv_category_id": "1", "tcgcsv_group_id": "11",
            "investment_product_type": "Bundle", "approval_status": "approved", "notes": "",
        },
        {
            "investment_product_id": "OLD-SL", "box_name": "Mapped Secret Lair",
            "approved_product_name": "Mapped Secret Lair", "approved_tcgplayer_product_id": "200",
            "tcgcsv_category_id": "3", "tcgcsv_group_id": "20",
            "investment_product_type": "Secret Lair Drop", "approval_status": "approved", "notes": "",
        },
    ])
    _write(secret_lairs, [
        {"secret_lair_id": "SL-1", "product_name": "Mapped Secret Lair", "tcgplayer_product_id": "200", "notes": ""},
        {"secret_lair_id": "SL-2", "product_name": "eBay Only Secret Lair", "tcgplayer_product_id": "201", "notes": ""},
    ])
    _write(review, [{"secret_lair_id": "SL-R", "product_name": "Review"}])

    output = tmp_path / "map.csv"
    summary = tmp_path / "summary.json"
    payload = build_full_product_map(products, secret_lairs, review, output, summary)

    assert payload["status"] == "PASS"
    assert payload["booster_display_count"] == 1
    assert payload["secret_lair_count"] == 2
    assert payload["total_marketplace_products"] == 3
    assert payload["ebay_ready_count"] == 3
    assert payload["tcgcsv_ready_count"] == 2
    assert payload["ebay_only_count"] == 1
    assert payload["review_excluded_count"] == 1

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert {row["investment_product_type"] for row in rows} == {
        "Collector Booster Display", "Secret Lair Sealed Product"
    }
    ebay_only = next(row for row in rows if row["tcgplayer_product_id"] == "201")
    assert ebay_only["mapping_status"] == "READY"
    assert ebay_only["collection_lane"] == "EBAY_ONLY"
    assert json.loads(summary.read_text(encoding="utf-8"))["total_marketplace_products"] == 3


def test_source_routing_keeps_ebay_only_rows_out_of_tcgcsv(tmp_path: Path) -> None:
    product_map = tmp_path / "full_product_map.csv"
    _write(product_map, [
        {
            "box_name": "Mapped Product", "tcgplayer_product_id": "100",
            "tcgcsv_category_id": "1", "tcgcsv_group_id": "10",
            "mapping_status": "READY", "collection_lane": "EBAY_AND_TCGCSV",
        },
        {
            "box_name": "eBay Only Product", "tcgplayer_product_id": "200",
            "tcgcsv_category_id": "", "tcgcsv_group_id": "",
            "mapping_status": "READY", "collection_lane": "EBAY_ONLY",
        },
    ])

    ebay_map, tcgcsv_map, routing = _split_collection_maps(product_map, tmp_path / "runtime")
    ebay_rows = list(csv.DictReader(ebay_map.open(encoding="utf-8")))
    tcgcsv_rows = list(csv.DictReader(tcgcsv_map.open(encoding="utf-8")))

    assert routing["status"] == "PASS"
    assert routing["ebay_product_count"] == 2
    assert routing["tcgcsv_product_count"] == 1
    assert routing["ebay_only_product_count"] == 1
    assert {row["tcgplayer_product_id"] for row in ebay_rows} == {"100", "200"}
    assert [row["tcgplayer_product_id"] for row in tcgcsv_rows] == ["100"]


def test_duplicate_identity_across_sources_is_not_duplicated(tmp_path: Path) -> None:
    products = tmp_path / "products.csv"
    secret_lairs = tmp_path / "secret_lairs.csv"
    _write(products, [{
        "investment_product_id": "IP-1", "box_name": "Box", "approved_product_name": "Box",
        "approved_tcgplayer_product_id": "123", "tcgcsv_category_id": "1", "tcgcsv_group_id": "99",
        "approval_status": "approved", "investment_product_type": "Collector Booster Display", "notes": "",
    }])
    _write(secret_lairs, [{"secret_lair_id": "SL-1", "product_name": "Duplicate", "tcgplayer_product_id": "123", "notes": ""}])
    payload = build_full_product_map(products, secret_lairs, None, tmp_path / "map.csv", tmp_path / "summary.json")
    assert payload["total_marketplace_products"] == 1


def test_batch_ranges_cover_entire_universe_without_overlap() -> None:
    ranges = _batch_ranges(1227, 50)
    assert len(ranges) == 25
    assert ranges[0] == (0, 50)
    assert ranges[-1] == (1200, 1227)
    covered = [index for start, end in ranges for index in range(start, end)]
    assert covered == list(range(1227))
