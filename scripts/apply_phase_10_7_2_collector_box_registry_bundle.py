from __future__ import annotations

from pathlib import Path

FILES: dict[str, str] = {
    "terminal2/registry/collector_booster_boxes.py": r'''from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

EXPECTED_ROWS = 49
EXPECTED_CLASS = "COLLECTOR_BOOSTER_BOX"
REQUIRED_COLUMNS = {
    "canonical_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "product_class",
    "tcgplayer_product_id",
    "release_date",
    "ebay_query",
}


def normalize_name(value: str) -> str:
    text = value.casefold().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing columns in {path}: {sorted(missing)}")
        return [dict(row) for row in reader]


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(materialized[0].keys()))
        writer.writeheader()
        writer.writerows(materialized)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_governed_registry(
    *,
    batch_one_path: Path,
    batch_two_path: Path,
    batch_one_coverage_path: Path,
    batch_two_coverage_path: Path,
    output_root: Path,
) -> dict[str, object]:
    batch_one = _read_csv(batch_one_path)
    batch_two = _read_csv(batch_two_path)
    coverage_one = _read_csv(batch_one_coverage_path)
    coverage_two = _read_csv(batch_two_coverage_path)

    tagged_rows: list[dict[str, str]] = []
    for label, rows in (("0000_0024", batch_one), ("0025_0048", batch_two)):
        for row in rows:
            tagged_rows.append({**row, "source_batch": label})

    all_rows = sorted(tagged_rows, key=lambda row: row["canonical_product_id"])
    coverage_rows = coverage_one + coverage_two

    ids = [row["canonical_product_id"].strip() for row in all_rows]
    names = [row["canonical_product_name"].strip() for row in all_rows]
    normalized_names = [normalize_name(name) for name in names]
    tcg_ids = [row["tcgplayer_product_id"].strip() for row in all_rows]
    classes = [row["product_class"].strip() for row in all_rows]
    queries = [row["ebay_query"].strip() for row in all_rows]
    coverage_ids = {
        row["canonical_product_id"].strip()
        for row in coverage_rows
        if row.get("canonical_product_id")
    }

    checks = {
        "rows_equal_49": len(all_rows) == EXPECTED_ROWS,
        "batch_rows_equal_25_and_24": len(batch_one) == 25 and len(batch_two) == 24,
        "canonical_ids_unique": len(ids) == len(set(ids)) == EXPECTED_ROWS,
        "normalized_names_unique": len(normalized_names) == len(set(normalized_names)) == EXPECTED_ROWS,
        "tcgplayer_ids_unique": len(tcg_ids) == len(set(tcg_ids)) == EXPECTED_ROWS,
        "all_classes_collector_booster_box": all(value == EXPECTED_CLASS for value in classes),
        "all_ids_nonempty": all(ids),
        "all_names_nonempty": all(names),
        "all_set_names_nonempty": all(row["canonical_set_name"].strip() for row in all_rows),
        "all_ebay_queries_nonempty": all(queries),
        "coverage_rows_equal_49": len(coverage_rows) == EXPECTED_ROWS,
        "coverage_ids_match_registry": coverage_ids == set(ids),
        "quota_calls_zero": True,
    }

    registry_rows: list[dict[str, object]] = []
    for row in all_rows:
        registry_rows.append(
            {
                "canonical_product_id": row["canonical_product_id"].strip(),
                "canonical_product_name": row["canonical_product_name"].strip(),
                "normalized_product_name": normalize_name(row["canonical_product_name"]),
                "canonical_set_name": row["canonical_set_name"].strip(),
                "product_class": EXPECTED_CLASS,
                "tcgplayer_product_id": row["tcgplayer_product_id"].strip(),
                "release_date": row["release_date"].strip(),
                "ebay_query": row["ebay_query"].strip(),
                "source_batch": row["source_batch"],
                "registry_status": "GOVERNED",
                "market_coverage_status": "COVERED" if row["canonical_product_id"].strip() in coverage_ids else "MISSING",
            }
        )

    output_root.mkdir(parents=True, exist_ok=True)
    registry_path = output_root / "collector_booster_box_governed_registry.csv"
    manifest_path = output_root / "collector_booster_box_registry_manifest.json"
    certification_path = output_root / "PHASE_10_7_2_COLLECTOR_BOX_REGISTRY_CERTIFICATION.md"

    _write_csv(registry_path, registry_rows)

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    manifest: dict[str, object] = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10.7.2",
        "lane": "COLLECTOR_BOOSTER_BOX",
        "products": len(registry_rows),
        "source_batches": {"0000_0024": len(batch_one), "0025_0048": len(batch_two)},
        "coverage_rows": len(coverage_rows),
        "quota_calls": 0,
        "checks": checks,
        "outputs": {
            "registry": str(registry_path.resolve()),
            "manifest": str(manifest_path.resolve()),
            "certification": str(certification_path.resolve()),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    lines = [
        "# Phase 10.7.2 Collector Booster Box Registry Certification",
        "",
        f"**Status:** {status}",
        "",
        f"- Governed products: {len(registry_rows)}",
        f"- Batch 0000_0024: {len(batch_one)}",
        f"- Batch 0025_0048: {len(batch_two)}",
        f"- Coverage rows: {len(coverage_rows)}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    certification_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "CERTIFIED":
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Collector Booster Box registry certification failed: {failed}")

    return manifest
''',
    "scripts/build_collector_booster_box_governed_registry.py": r'''from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from terminal2.registry.collector_booster_boxes import build_governed_registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-one", type=Path, required=True)
    parser.add_argument("--batch-two", type=Path, required=True)
    parser.add_argument("--batch-one-coverage", type=Path, required=True)
    parser.add_argument("--batch-two-coverage", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    result = build_governed_registry(
        batch_one_path=args.batch_one,
        batch_two_path=args.batch_two,
        batch_one_coverage_path=args.batch_one_coverage,
        batch_two_coverage_path=args.batch_two_coverage,
        output_root=args.output_root,
    )
    print("PHASE 10.7.2 COLLECTOR BOX REGISTRY: COMPLETE")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
''',
    "tests/test_collector_booster_box_governed_registry.py": r'''from __future__ import annotations

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
''',
    "docs/phase_10/PHASE_10_7_2_COLLECTOR_BOX_REGISTRY.md": r'''# Phase 10.7.2 — Collector Booster Box Governed Registry

This milestone consolidates the two certified Collector Booster Box eBay batch universes into one governed 49-product registry.

Certification requires:

- 25 products in batch `0000_0024`
- 24 products in batch `0025_0048`
- 49 unique canonical product IDs
- 49 unique normalized product names
- 49 unique TCGplayer product IDs
- every product classified as `COLLECTOR_BOOSTER_BOX`
- complete canonical names, set names, and eBay queries
- exact registry-to-coverage reconciliation
- zero API quota calls

Generated registry and certification files remain local under `data/validation/phase_10/collector_booster_boxes/governed_registry/`.
''',
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path, content in FILES.items():
        target = root / relative_path
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"Created: {relative_path}")
    print("PHASE 10.7.2 COLLECTOR BOX REGISTRY BUNDLE: APPLIED")


if __name__ == "__main__":
    main()
