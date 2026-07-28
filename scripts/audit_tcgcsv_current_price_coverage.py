from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_MAP = ROOT / "data/operations/mtg_tcgcsv_price_backfill/confirmed_tcgcsv_product_map.csv"
OBSERVATIONS = ROOT / "data/operations/mtg_tcgcsv_price_backfill/current/tcgcsv_current_price_observations.csv"
OUTPUT = ROOT / "data/operations/mtg_tcgcsv_price_backfill/current"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(map_rows: list[dict[str, str]], observation_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    observed_ids = {row["investment_product_id"] for row in observation_rows}
    missing = []
    for row in map_rows:
        if row["investment_product_id"] in observed_ids:
            continue
        missing.append({
            "investment_product_id": row["investment_product_id"],
            "box_name": row["box_name"],
            "source_product_name": row["source_product_name"],
            "tcgplayer_product_id": row["tcgplayer_product_id"],
            "tcgcsv_category_id": row["tcgcsv_category_id"],
            "tcgcsv_group_id": row["tcgcsv_group_id"],
            "current_price_status": "NO_USABLE_CURRENT_PRICE",
            "historical_backfill_required": "YES",
            "fallback_route": "EBAY_LIVE",
        })

    summary = {
        "status": "PASS",
        "confirmed_map_rows": len(map_rows),
        "current_observation_rows": len(observation_rows),
        "products_with_current_price": len(observed_ids),
        "products_without_current_price": len(missing),
        "coverage_rate": round(len(observed_ids) / len(map_rows), 6) if map_rows else 0,
        "certification_checks": {
            "confirmed_map_rows_equal_871": len(map_rows) == 871,
            "all_observations_map_to_confirmed_products": observed_ids <= {row["investment_product_id"] for row in map_rows},
            "coverage_reconciles_to_871": len(observed_ids) + len(missing) == 871,
            "missing_rows_unique": len({row["investment_product_id"] for row in missing}) == len(missing),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"
    return missing, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit current-price coverage for confirmed TCGCSV identities.")
    parser.add_argument("--product-map", type=Path, default=PRODUCT_MAP)
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    missing, summary = build(
        read_csv(args.product_map.resolve()),
        read_csv(args.observations.resolve()),
    )
    output = args.output_root.resolve()
    write_csv(
        output / "tcgcsv_current_price_missing_products.csv",
        missing,
        [
            "investment_product_id", "box_name", "source_product_name",
            "tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id",
            "current_price_status", "historical_backfill_required", "fallback_route",
        ],
    )
    (output / "tcgcsv_current_price_coverage_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
