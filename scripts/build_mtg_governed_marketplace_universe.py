from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data" / "reference" / "phase_11" / "mtg_hosted_baseline"
DEFAULT_OVERRIDES = ROOT / "data" / "reference" / "product_map.csv"
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_marketplace" / "governed_universe"

REGISTRIES = (
    ("SECRET_LAIR", BASELINE / "secret_lair_registry.csv"),
    ("COLLECTOR_BOOSTER_BOX", BASELINE / "collector_registry.csv"),
    ("PRE_COLLECTOR_BOOSTER_BOX", BASELINE / "pre_collector_registry.csv"),
)

EXPECTED = {
    "SECRET_LAIR": 973,
    "COLLECTOR_BOOSTER_BOX": 49,
    "PRE_COLLECTOR_BOOSTER_BOX": 119,
}

FIELDS = (
    "canonical_product_id",
    "box_name",
    "source_product_name",
    "product_class",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "scryfall_set_code",
    "ebay_query",
    "collection_lane",
    "mapping_status",
    "registry_status",
    "source_registry",
    "manual_override_applied",
    "notes",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def first(row: dict[str, str], *fields: str) -> str:
    for field in fields:
        value = str(row.get(field, "") or "").strip()
        if value:
            return value
    return ""


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def ebay_query(name: str, product_class: str, provided: str = "") -> str:
    if provided.strip():
        return provided.strip()
    quoted = name.replace('"', "")
    if product_class == "SECRET_LAIR":
        return f'Magic The Gathering Secret Lair "{quoted}" sealed'
    return f'Magic The Gathering "{quoted}" sealed'


def load_overrides(path: Path):
    by_id = {}
    by_name = {}
    if not path.is_file():
        return by_id, by_name
    for row in read_csv(path):
        product_id = first(row, "tcgplayer_product_id")
        name = first(row, "box_name", "source_product_name")
        if product_id:
            by_id[product_id] = row
        if name:
            by_name[normalized(name)] = row
    return by_id, by_name


def build_rows(overrides_path: Path):
    override_by_id, override_by_name = load_overrides(overrides_path)
    rows = []
    lane_counts = Counter()
    override_count = 0

    for product_class, registry_path in REGISTRIES:
        registry = read_csv(registry_path)
        if len(registry) != EXPECTED[product_class]:
            raise ValueError(
                f"{product_class} registry count {len(registry)} "
                f"does not equal expected {EXPECTED[product_class]}"
            )

        for source in registry:
            canonical_id = first(
                source,
                "canonical_product_id",
                "investment_product_id",
                "source_product_id",
                "product_id",
            )
            name = first(
                source,
                "canonical_product_name",
                "product_name",
                "name",
            )
            tcgplayer_id = first(
                source,
                "approved_tcgplayer_product_id",
                "tcgplayer_product_id",
                "tcgplayer_product_id_str",
            )
            override = (
                override_by_id.get(tcgplayer_id)
                or override_by_name.get(normalized(name))
                or {}
            )
            if override:
                override_count += 1

            final_name = first(
                override,
                "box_name",
                "source_product_name",
            ) or name
            final_tcgplayer_id = first(
                override,
                "tcgplayer_product_id",
            ) or tcgplayer_id

            if product_class == "SECRET_LAIR":
                lane = "EBAY_ONLY"
            elif final_tcgplayer_id:
                lane = "EBAY_AND_TCGCSV"
            else:
                lane = "EBAY_ONLY"

            row = {
                "canonical_product_id": canonical_id,
                "box_name": final_name,
                "source_product_name": first(
                    override, "source_product_name"
                ) or final_name,
                "product_class": product_class,
                "tcgplayer_product_id": final_tcgplayer_id,
                "tcgcsv_category_id": first(
                    override, "tcgcsv_category_id"
                ) or ("3" if final_tcgplayer_id else ""),
                "tcgcsv_group_id": first(
                    override, "tcgcsv_group_id"
                ),
                "scryfall_set_code": first(
                    override, "scryfall_set_code"
                ),
                "ebay_query": ebay_query(
                    final_name,
                    product_class,
                    first(source, "ebay_query"),
                ),
                "collection_lane": lane,
                "mapping_status": "READY" if canonical_id and final_name else "INCOMPLETE",
                "registry_status": first(
                    source, "registry_status"
                ) or "GOVERNED",
                "source_registry": registry_path.name,
                "manual_override_applied": "YES" if override else "NO",
                "notes": first(override, "notes"),
            }
            rows.append(row)
            lane_counts[lane] += 1

    ids = [row["canonical_product_id"] for row in rows]
    duplicate_ids = sorted(
        product_id
        for product_id, count in Counter(ids).items()
        if product_id and count > 1
    )
    missing_ids = [
        row["box_name"] for row in rows
        if not row["canonical_product_id"]
    ]
    incomplete = [
        row["canonical_product_id"] or row["box_name"]
        for row in rows
        if row["mapping_status"] != "READY"
    ]

    summary = {
        "status": (
            "PASS"
            if len(rows) == 1141
            and not duplicate_ids
            and not missing_ids
            and not incomplete
            else "FAIL"
        ),
        "total_products": len(rows),
        "expected_products": 1141,
        "product_class_counts": dict(
            sorted(Counter(row["product_class"] for row in rows).items())
        ),
        "collection_lane_counts": dict(sorted(lane_counts.items())),
        "tcgplayer_mapped_products": sum(
            bool(row["tcgplayer_product_id"]) for row in rows
        ),
        "ebay_eligible_products": sum(
            row["mapping_status"] == "READY" for row in rows
        ),
        "tcgcsv_eligible_products": sum(
            row["collection_lane"] == "EBAY_AND_TCGCSV"
            and bool(row["tcgplayer_product_id"])
            for row in rows
        ),
        "manual_override_count": override_count,
        "duplicate_canonical_product_ids": duplicate_ids,
        "missing_canonical_product_ids": missing_ids,
        "incomplete_products": incomplete,
        "source_registries": [
            str(path.resolve()) for _, path in REGISTRIES
        ],
        "manual_override_source": str(overrides_path.resolve()),
    }
    return rows, summary


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(FIELDS),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the governed Phase 11E MTG marketplace universe."
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=DEFAULT_OVERRIDES,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    rows, summary = build_rows(args.overrides.resolve())
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    write_csv(output / "governed_marketplace_product_map.csv", rows)
    write_csv(
        output / "ebay_eligible_product_map.csv",
        [row for row in rows if row["mapping_status"] == "READY"],
    )
    write_csv(
        output / "tcgcsv_eligible_product_map.csv",
        [
            row for row in rows
            if row["collection_lane"] == "EBAY_AND_TCGCSV"
            and row["tcgplayer_product_id"]
        ],
    )

    (output / "governed_marketplace_universe_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
