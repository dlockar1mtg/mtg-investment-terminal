from __future__ import annotations

import csv
from pathlib import Path

from terminal2.registry.pre_collector_booster_boxes import (
    EXPECTED_CLASS,
    EXPECTED_ROWS,
    build_governed_registry,
)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_rows(count: int = EXPECTED_ROWS) -> list[dict[str, str]]:
    return [
        {
            "canonical_product_id": f"PRE-{index:03d}",
            "canonical_product_name": f"Set {index:03d} - Booster Box",
            "canonical_set_name": f"Set {index:03d}",
            "product_class": EXPECTED_CLASS,
            "tcgplayer_product_id": str(100000 + index),
            "release_date": f"{1993 + index // 12:04d}-{index % 12 + 1:02d}-01",
            "ebay_query": f"Set {index:03d} booster box sealed",
        }
        for index in range(count)
    ]


def test_certifies_exact_governed_universe(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.csv"
    collector = tmp_path / "collector.csv"
    output = tmp_path / "output"
    write_csv(candidate, make_rows())
    write_csv(
        collector,
        [{
            "canonical_product_id": "COLLECTOR-001",
            "canonical_product_name": "Collector Product",
            "canonical_set_name": "Collector Set",
            "product_class": "COLLECTOR_BOOSTER_BOX",
            "tcgplayer_product_id": "999999",
            "release_date": "2020-01-01",
            "ebay_query": "collector",
        }],
    )
    manifest = build_governed_registry(candidate, collector, output)
    assert manifest["status"] == "CERTIFIED"
    assert manifest["products"] == EXPECTED_ROWS
    assert manifest["collector_registry_overlap"] == 0


def test_rejects_duplicate_identity(tmp_path: Path) -> None:
    rows = make_rows()
    rows[-1]["canonical_product_id"] = rows[0]["canonical_product_id"]
    candidate = tmp_path / "candidate.csv"
    collector = tmp_path / "collector.csv"
    write_csv(candidate, rows)
    write_csv(collector, make_rows(1))
    manifest = build_governed_registry(candidate, collector, tmp_path / "output")
    assert manifest["status"] == "FAILED"
    assert manifest["checks"]["canonical_ids_unique"] is False


def test_rejects_collector_leakage(tmp_path: Path) -> None:
    rows = make_rows()
    rows[0]["canonical_product_name"] = "Collector Booster Box"
    candidate = tmp_path / "candidate.csv"
    collector = tmp_path / "collector.csv"
    write_csv(candidate, rows)
    write_csv(collector, make_rows(1))
    manifest = build_governed_registry(candidate, collector, tmp_path / "output")
    assert manifest["status"] == "FAILED"
    assert manifest["checks"]["collector_leakage_zero"] is False
