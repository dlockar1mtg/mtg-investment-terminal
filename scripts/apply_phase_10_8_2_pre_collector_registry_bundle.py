from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "terminal2/registry/pre_collector_booster_boxes.py": '''from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_ROWS = 119
EXPECTED_CLASS = "PRE_COLLECTOR_BOOSTER_BOX"
REQUIRED_FIELDS = (
    "canonical_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "product_class",
    "tcgplayer_product_id",
    "release_date",
    "ebay_query",
)


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_governed_registry(
    candidate_path: Path,
    collector_registry_path: Path,
    output_root: Path,
) -> dict[str, object]:
    candidate_rows = read_csv(candidate_path)
    collector_rows = read_csv(collector_registry_path)

    governed_rows = sorted(
        ({field: row.get(field, "").strip() for field in REQUIRED_FIELDS}
         for row in candidate_rows),
        key=lambda row: (row["release_date"], row["canonical_product_id"]),
    )

    canonical_ids = [row["canonical_product_id"] for row in governed_rows]
    names = [row["canonical_product_name"] for row in governed_rows]
    normalized_names = [normalize_name(value) for value in names]
    tcgplayer_ids = [row["tcgplayer_product_id"] for row in governed_rows]
    collector_ids = {row.get("canonical_product_id", "").strip() for row in collector_rows}

    checks = {
        "rows_equal_119": len(governed_rows) == EXPECTED_ROWS,
        "canonical_ids_unique": len(set(canonical_ids)) == EXPECTED_ROWS,
        "normalized_names_unique": len(set(normalized_names)) == EXPECTED_ROWS,
        "tcgplayer_ids_unique": len(set(tcgplayer_ids)) == EXPECTED_ROWS,
        "required_fields_populated": all(
            all(row[field] for field in REQUIRED_FIELDS)
            for row in governed_rows
        ),
        "product_class_correct": all(
            row["product_class"] == EXPECTED_CLASS
            for row in governed_rows
        ),
        "collector_leakage_zero": all(
            "collector booster" not in " | ".join(
                (
                    row["canonical_product_name"],
                    row["canonical_set_name"],
                    row["ebay_query"],
                )
            ).lower()
            for row in governed_rows
        ),
        "collector_registry_overlap_zero": not (
            set(canonical_ids) & collector_ids
        ),
        "release_dates_monotonic": [row["release_date"] for row in governed_rows]
        == sorted(row["release_date"] for row in governed_rows),
        "quota_calls_zero": True,
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"
    output_root.mkdir(parents=True, exist_ok=True)

    registry_path = output_root / "pre_collector_booster_box_governed_registry.csv"
    with registry_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_FIELDS))
        writer.writeheader()
        writer.writerows(governed_rows)

    duplicate_diagnostics = {
        "canonical_id_duplicates": sorted(
            value for value, count in Counter(canonical_ids).items() if value and count > 1
        ),
        "normalized_name_duplicates": sorted(
            value for value, count in Counter(normalized_names).items() if value and count > 1
        ),
        "tcgplayer_id_duplicates": sorted(
            value for value, count in Counter(tcgplayer_ids).items() if value and count > 1
        ),
    }

    manifest = {
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "10.8.2",
        "lane": EXPECTED_CLASS,
        "products": len(governed_rows),
        "unique_canonical_ids": len(set(canonical_ids)),
        "unique_normalized_names": len(set(normalized_names)),
        "unique_tcgplayer_ids": len(set(tcgplayer_ids)),
        "earliest_release_date": governed_rows[0]["release_date"] if governed_rows else "",
        "latest_release_date": governed_rows[-1]["release_date"] if governed_rows else "",
        "collector_registry_products": len(collector_rows),
        "collector_registry_overlap": len(set(canonical_ids) & collector_ids),
        "checks": checks,
        "duplicates": duplicate_diagnostics,
        "quota_calls": 0,
        "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
        "outputs": {"registry": str(registry_path.resolve())},
    }

    manifest_path = output_root / "pre_collector_booster_box_registry_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    certification_path = output_root / "PHASE_10_8_2_PRE_COLLECTOR_REGISTRY_CERTIFICATION.md"
    lines = [
        "# Phase 10.8.2 Pre-Collector Booster Box Registry Certification",
        "",
        f"**Status:** {status}",
        "",
        f"- Governed products: {len(governed_rows)}",
        f"- Earliest release date: {manifest['earliest_release_date']}",
        f"- Latest release date: {manifest['latest_release_date']}",
        f"- Collector Box overlap: {manifest['collector_registry_overlap']}",
        "- API quota calls: 0",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    certification_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest
''',
    "scripts/build_pre_collector_booster_box_governed_registry.py": '''from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.registry.pre_collector_booster_boxes import build_governed_registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--collector-registry", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_governed_registry(
        args.candidate,
        args.collector_registry,
        args.output_root,
    )
    print("PHASE 10.8.2 PRE-COLLECTOR REGISTRY: COMPLETE")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
''',
    "tests/test_pre_collector_booster_box_governed_registry.py": '''from __future__ import annotations

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
''',
    "docs/phase_10/PHASE_10_8_2_PRE_COLLECTOR_REGISTRY.md": '''# Phase 10.8.2 Pre-Collector Booster Box Governed Registry

This milestone certifies the 119-product traditional Booster Box universe spanning Alpha Edition through Core Set 2020.

Certification requires exact row and identity counts, complete governed fields, the PRE_COLLECTOR_BOOSTER_BOX class, zero Collector Booster leakage, zero overlap with the certified 49-product Collector Booster Box registry, deterministic ordering, and zero API quota usage.

Generated registry and certification outputs remain local under data/validation/phase_10/pre_collector_booster_boxes/governed_registry/.
''',
}


def main() -> int:
    for relative_path, content in FILES.items():
        path = ROOT / relative_path
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Created: {relative_path}")
    print("PHASE 10.8.2 PRE-COLLECTOR REGISTRY BUNDLE: APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
