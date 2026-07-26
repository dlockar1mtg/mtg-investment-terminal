"""Governed command-line wrapper for daily TCGCSV price collection.

Dry-run mode validates inputs and emits evidence without making network calls.
Live mode delegates to collectors.tcgcsv_collector.collect_tcgcsv_prices.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed daily TCGCSV collection")
    parser.add_argument("--product-map", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=Path("data/operations/tcgcsv/daily_collection.json"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _publish(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    product_map = args.product_map.resolve()
    payload: dict[str, object] = {
        "status": "DRY_RUN" if args.dry_run else "STARTING",
        "live_api_called": False,
        "product_map": str(product_map),
        "product_map_available": product_map.is_file(),
    }

    if not product_map.is_file():
        payload["status"] = "FAILED"
        payload["reason_codes"] = ["TCGCSV_PRODUCT_MAP_NOT_AVAILABLE"]
        _publish(args.summary_output, payload)
        print(json.dumps(payload, indent=2))
        return 1

    if args.dry_run:
        payload["reason_codes"] = ["TCGCSV_DRY_RUN_VALIDATED"]
        _publish(args.summary_output, payload)
        print(json.dumps(payload, indent=2))
        return 0

    from collectors.tcgcsv_collector import collect_tcgcsv_prices

    frame = collect_tcgcsv_prices(product_map)
    payload.update(
        {
            "status": "PASS",
            "live_api_called": True,
            "rows_collected": int(len(frame)),
            "reason_codes": ["TCGCSV_COLLECTION_COMPLETED"],
        }
    )
    _publish(args.summary_output, payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
