from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESOLUTION = ROOT / "data/operations/mtg_source_discovery/universal_tcgcsv_discovery/universal_tcgcsv_identity_resolution.csv"
OUTPUT = ROOT / "data/operations/mtg_tcgcsv_price_backfill"

MAP_FIELDS = [
    "investment_product_id",
    "box_name",
    "source_product_name",
    "product_class",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "mapping_status",
    "discovery_status",
    "automatic_collection_allowed",
]

STATUS_FIELDS = [
    "investment_product_id",
    "canonical_product_name",
    "finish_group",
    "product_group",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "discovery_status",
    "automatic_collection_allowed",
    "current_price_route",
    "historical_price_route",
    "fallback_route",
    "reason_code",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if len(rows) != 973:
        raise ValueError(f"Expected 973 identity rows; found {len(rows)}")

    maps: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []

    for row in rows:
        status = str(row.get("discovery_status") or "").strip()
        confirmed = status == "TCGCSV_ID_CONFIRMED"
        has_ids = all(
            str(row.get(name) or "").strip()
            for name in ("tcgplayer_product_id", "tcgcsv_group_id")
        )
        allowed = confirmed and has_ids

        if allowed:
            maps.append({
                "investment_product_id": row["investment_product_id"],
                "box_name": row["canonical_product_name"],
                "source_product_name": row["tcgcsv_product_name"],
                "product_class": "SECRET_LAIR",
                "tcgplayer_product_id": row["tcgplayer_product_id"],
                "tcgcsv_category_id": "1",
                "tcgcsv_group_id": row["tcgcsv_group_id"],
                "mapping_status": "READY",
                "discovery_status": status,
                "automatic_collection_allowed": "YES",
            })

        if status == "TCGCSV_ID_CONFIRMED":
            current_route = "TCGCSV_LIVE"
            historical_route = "TCGCSV_ARCHIVE_MONTHLY"
            fallback = "EBAY_LIVE"
            reason = "CONFIRMED_IDENTITY"
        elif status == "TCGCSV_ID_AMBIGUOUS":
            current_route = "BLOCKED_PENDING_REVIEW"
            historical_route = "BLOCKED_PENDING_REVIEW"
            fallback = "EBAY_LIVE"
            reason = "AMBIGUOUS_IDENTITY"
        else:
            current_route = "NO_TCGCSV_ROUTE"
            historical_route = "NO_TCGCSV_ROUTE"
            fallback = "EBAY_LIVE"
            reason = "TCGCSV_ID_NOT_FOUND"

        statuses.append({
            "investment_product_id": row["investment_product_id"],
            "canonical_product_name": row["canonical_product_name"],
            "finish_group": row["finish_group"],
            "product_group": row["product_group"],
            "tcgplayer_product_id": row.get("tcgplayer_product_id", "") if allowed else "",
            "tcgcsv_category_id": "1" if allowed else "",
            "tcgcsv_group_id": row.get("tcgcsv_group_id", "") if allowed else "",
            "discovery_status": status,
            "automatic_collection_allowed": "YES" if allowed else "NO",
            "current_price_route": current_route,
            "historical_price_route": historical_route,
            "fallback_route": fallback,
            "reason_code": reason,
        })

    duplicate_ids = [
        pid for pid, count in Counter(row["tcgplayer_product_id"] for row in maps).items()
        if count > 1
    ]
    status_counts = Counter(row["discovery_status"] for row in statuses)

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "identity_rows": len(rows),
        "confirmed_map_rows": len(maps),
        "status_matrix_rows": len(statuses),
        "discovery_status_counts": dict(sorted(status_counts.items())),
        "unique_confirmed_tcgplayer_ids": len({row["tcgplayer_product_id"] for row in maps}),
        "unique_confirmed_group_ids": len({row["tcgcsv_group_id"] for row in maps}),
        "duplicate_confirmed_tcgplayer_ids": duplicate_ids,
        "certification_checks": {
            "identity_rows_equal_973": len(rows) == 973,
            "status_matrix_rows_equal_973": len(statuses) == 973,
            "confirmed_map_rows_equal_confirmed_status": len(maps) == status_counts.get("TCGCSV_ID_CONFIRMED", 0),
            "no_ambiguous_ids_in_automatic_map": not any(
                row["discovery_status"] != "TCGCSV_ID_CONFIRMED" for row in maps
            ),
            "confirmed_tcgplayer_ids_unique": not duplicate_ids,
            "all_rows_have_fallback_route": all(row["fallback_route"] for row in statuses),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"
    return maps, statuses, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the governed Phase 11E.7 TCGCSV price-backfill map.")
    parser.add_argument("--resolution", type=Path, default=RESOLUTION)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    maps, statuses, summary = build(read_csv(args.resolution.resolve()))
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "confirmed_tcgcsv_product_map.csv", maps, MAP_FIELDS)
    write_csv(output / "universal_tcgcsv_price_route_status.csv", statuses, STATUS_FIELDS)
    (output / "tcgcsv_price_backfill_map_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
