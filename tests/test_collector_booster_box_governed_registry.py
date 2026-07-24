from __future__ import annotations

import csv
from pathlib import Path

import pytest

from terminal2.registry.collector_booster_boxes import build_governed_registry, normalize_name

FIELDS = [
    "canonical_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "product_class",
    "tcgplayer_product_id",
    "release_date",
    "ebay_query",
]


def write_rows(path: Path, start: int, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for index in range(start, start + count):
            writer.writerow(
                {
                    "canonical_product_id": f"TCGCSV-{index}-{100000 + index}",
                    "canonical_product_name": f"Set {index} Collector Booster Display",
                    "canonical_set_name": f"Set {index}",
                    "product_class": "COLLECTOR_BOOSTER_BOX",
                    "tcgplayer_product_id": str(100000 + index),
                    "release_date": "",
                    "ebay_query": f'Magic The Gathering "Set {index} Collector Booster Display" sealed',
                }
            )


def test_normalize_name_is_deterministic() -> None:
    assert normalize_name("  Marvel's Spider-Man Collector Booster Display  ") == "marvel s spider man collector booster display"


def test_build_governed_registry_certifies_49_rows(tmp_path: Path) -> None:
    batch_one = tmp_path / "batch_one.csv"
    batch_two = tmp_path / "batch_two.csv"
    coverage_one = tmp_path / "coverage_one.csv"
    coverage_two = tmp_path / "coverage_two.csv"
    output_root = tmp_path / "output"

    write_rows(batch_one, 0, 25)
    write_rows(batch_two, 25, 24)
    write_rows(coverage_one, 0, 25)
    write_rows(coverage_two, 25, 24)

    result = build_governed_registry(
        batch_one_path=batch_one,
        batch_two_path=batch_two,
        batch_one_coverage_path=coverage_one,
        batch_two_coverage_path=coverage_two,
        output_root=output_root,
    )

    assert result["status"] == "CERTIFIED"
    assert result["products"] == 49
    assert all(result["checks"].values())


def test_duplicate_id_fails_certification(tmp_path: Path) -> None:
    batch_one = tmp_path / "batch_one.csv"
    batch_two = tmp_path / "batch_two.csv"
    coverage_one = tmp_path / "coverage_one.csv"
    coverage_two = tmp_path / "coverage_two.csv"
    write_rows(batch_one, 0, 25)
    write_rows(batch_two, 24, 24)
    write_rows(coverage_one, 0, 25)
    write_rows(coverage_two, 24, 24)

    with pytest.raises(RuntimeError):
        build_governed_registry(
            batch_one_path=batch_one,
            batch_two_path=batch_two,
            batch_one_coverage_path=coverage_one,
            batch_two_coverage_path=coverage_two,
            output_root=tmp_path / "output",
        )
