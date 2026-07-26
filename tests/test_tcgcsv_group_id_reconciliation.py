from __future__ import annotations

import csv
from pathlib import Path

from scripts.reconcile_tcgcsv_group_ids import reconcile


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_reconcile_resolves_unique_exact_product_id_match(tmp_path: Path) -> None:
    product_map = tmp_path / "data" / "reference" / "product_map.csv"
    _write_csv(
        product_map,
        [{
            "box_name": "Example Box",
            "tcgplayer_product_id": "123",
            "tcgcsv_category_id": "3",
            "tcgcsv_group_id": "",
        }],
    )
    _write_csv(
        tmp_path / "data" / "staging" / "snapshot.csv",
        [{"tcgplayer_product_id": "123", "tcgcsv_category_id": "3", "tcgcsv_group_id": "999"}],
    )

    report = reconcile(product_map, tmp_path / "data")

    assert report["status"] == "PASS"
    assert report["resolved_products"] == 1
    assert report["results"][0]["selected_group_id"] == "999"


def test_reconcile_fails_closed_on_ambiguous_group_ids(tmp_path: Path) -> None:
    product_map = tmp_path / "data" / "reference" / "product_map.csv"
    _write_csv(
        product_map,
        [{
            "box_name": "Example Box",
            "tcgplayer_product_id": "123",
            "tcgcsv_category_id": "3",
            "tcgcsv_group_id": "",
        }],
    )
    _write_csv(
        tmp_path / "data" / "staging" / "one.csv",
        [{"tcgplayer_product_id": "123", "tcgcsv_category_id": "3", "tcgcsv_group_id": "999"}],
    )
    _write_csv(
        tmp_path / "data" / "validation" / "two.csv",
        [{"tcgplayer_product_id": "123", "tcgcsv_category_id": "3", "tcgcsv_group_id": "1000"}],
    )

    report = reconcile(product_map, tmp_path / "data")

    assert report["status"] == "INCOMPLETE"
    assert report["ambiguous_products"] == 1
    assert report["results"][0]["selected_group_id"] == ""


def test_reconcile_does_not_use_name_only_matches(tmp_path: Path) -> None:
    product_map = tmp_path / "data" / "reference" / "product_map.csv"
    _write_csv(
        product_map,
        [{
            "box_name": "Example Box",
            "tcgplayer_product_id": "123",
            "tcgcsv_category_id": "3",
            "tcgcsv_group_id": "",
        }],
    )
    _write_csv(
        tmp_path / "data" / "staging" / "snapshot.csv",
        [{"box_name": "Example Box", "tcgplayer_product_id": "456", "tcgcsv_group_id": "999"}],
    )

    report = reconcile(product_map, tmp_path / "data")

    assert report["status"] == "INCOMPLETE"
    assert report["unresolved_products"] == 1
    assert report["results"][0]["evidence"] == []
