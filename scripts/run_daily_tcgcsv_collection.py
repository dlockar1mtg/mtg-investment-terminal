"""Governed command-line wrapper for daily TCGCSV price collection.

Dry-run mode validates mapping completeness and emits evidence without making
network calls. Live mode delegates to collectors.tcgcsv_collector and persists
collected observations for downstream normalization.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_COLUMNS = (
    "box_name",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed daily TCGCSV collection")
    parser.add_argument("--product-map", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=Path("data/operations/tcgcsv/daily_collection.json"))
    parser.add_argument("--observations-output", type=Path, default=Path("data/operations/tcgcsv/price_observations.csv"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _publish(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _inspect_product_map(path: Path) -> tuple[int, int, list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        missing_columns = [name for name in REQUIRED_COLUMNS if name not in columns]
        if missing_columns:
            return 0, 0, missing_columns

        total_rows = 0
        complete_rows = 0
        for row in reader:
            total_rows += 1
            if all(str(row.get(name) or "").strip() for name in REQUIRED_COLUMNS):
                complete_rows += 1
        return total_rows, complete_rows, []


def main() -> int:
    args = build_parser().parse_args()
    product_map = args.product_map.resolve()
    observations_output = args.observations_output.resolve()
    payload: dict[str, object] = {
        "status": "DRY_RUN" if args.dry_run else "STARTING",
        "live_api_called": False,
        "product_map": str(product_map),
        "product_map_available": product_map.is_file(),
        "observations_output": str(observations_output),
    }

    if not product_map.is_file():
        payload["status"] = "FAILED"
        payload["reason_codes"] = ["TCGCSV_PRODUCT_MAP_NOT_AVAILABLE"]
        _publish(args.summary_output, payload)
        print(json.dumps(payload, indent=2))
        return 1

    total_rows, complete_rows, missing_columns = _inspect_product_map(product_map)
    payload.update(
        {
            "product_map_rows": total_rows,
            "complete_mapping_rows": complete_rows,
            "missing_required_columns": missing_columns,
        }
    )

    if missing_columns:
        payload["status"] = "FAILED"
        payload["reason_codes"] = ["TCGCSV_PRODUCT_MAP_SCHEMA_INVALID"]
        _publish(args.summary_output, payload)
        print(json.dumps(payload, indent=2))
        return 1

    if complete_rows == 0:
        payload["status"] = "INCOMPLETE"
        payload["reason_codes"] = ["TCGCSV_NO_COMPLETE_PRODUCT_MAPPINGS"]
        _publish(args.summary_output, payload)
        print(json.dumps(payload, indent=2))
        return 2

    if args.dry_run:
        payload["reason_codes"] = ["TCGCSV_DRY_RUN_VALIDATED"]
        _publish(args.summary_output, payload)
        print(json.dumps(payload, indent=2))
        return 0

    from collectors.tcgcsv_collector import collect_tcgcsv_prices

    frame = collect_tcgcsv_prices(product_map)
    observations_output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(observations_output, index=False)
    payload.update(
        {
            "status": "PASS" if len(frame) else "INCOMPLETE",
            "live_api_called": True,
            "rows_collected": int(len(frame)),
            "observations_written": observations_output.is_file(),
            "reason_codes": ["TCGCSV_COLLECTION_COMPLETED"] if len(frame) else ["TCGCSV_COLLECTION_RETURNED_NO_ROWS"],
        }
    )
    _publish(args.summary_output, payload)
    print(json.dumps(payload, indent=2))
    return 0 if len(frame) else 2


if __name__ == "__main__":
    raise SystemExit(main())
