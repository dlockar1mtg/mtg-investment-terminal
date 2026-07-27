from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = (
    ROOT
    / "data"
    / "operations"
    / "mtg_marketplace"
    / "governed_universe"
    / "governed_marketplace_product_map.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "mtg_marketplace"
    / "runtime"
    / "marketplace_batch_product_map.csv"
)
DEFAULT_SUMMARY = (
    ROOT
    / "data"
    / "operations"
    / "mtg_marketplace"
    / "runtime"
    / "marketplace_batch_summary.json"
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def choose_batch(
    rows: list[dict[str, str]],
    *,
    batch_size: int,
    run_number: int,
    requested_batch_index: int | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if run_number < 1:
        raise ValueError("run_number must be positive")

    ready = [
        dict(row)
        for row in rows
        if str(row.get("mapping_status") or "").upper() == "READY"
    ]
    ready.sort(
        key=lambda row: (
            str(row.get("product_class") or ""),
            str(row.get("canonical_product_id") or ""),
        )
    )

    batch_count = max(1, math.ceil(len(ready) / batch_size))
    if requested_batch_index is None:
        batch_index = (run_number - 1) % batch_count
        selection_mode = "ROTATING_RUN_NUMBER"
    else:
        if requested_batch_index < 0 or requested_batch_index >= batch_count:
            raise ValueError(
                f"batch_index must be between 0 and {batch_count - 1}"
            )
        batch_index = requested_batch_index
        selection_mode = "EXPLICIT_BATCH_INDEX"

    start = batch_index * batch_size
    stop = min(start + batch_size, len(ready))
    ebay_batch = ready[start:stop]
    ebay_ids = {
        str(row.get("canonical_product_id") or "")
        for row in ebay_batch
    }

    runtime_rows: list[dict[str, str]] = []
    for source in ready:
        row = dict(source)
        canonical_id = str(row.get("canonical_product_id") or "")
        original_lane = str(
            row.get("collection_lane") or "EBAY_ONLY"
        ).upper()

        if canonical_id in ebay_ids:
            row["collection_lane"] = original_lane
            row["batch_role"] = "EBAY_BATCH"
            runtime_rows.append(row)
        elif (
            original_lane == "EBAY_AND_TCGCSV"
            and str(row.get("tcgplayer_product_id") or "").strip()
        ):
            row["collection_lane"] = "TCGCSV_ONLY"
            row["batch_role"] = "TCGCSV_FULL_REFRESH"
            runtime_rows.append(row)

    summary = {
        "status": "PASS",
        "selection_mode": selection_mode,
        "run_number": run_number,
        "batch_size": batch_size,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "universe_ready_products": len(ready),
        "ebay_batch_products": len(ebay_batch),
        "tcgcsv_full_refresh_products": sum(
            str(row.get("collection_lane") or "").upper()
            in {"EBAY_AND_TCGCSV", "TCGCSV_ONLY"}
            and bool(str(row.get("tcgplayer_product_id") or "").strip())
            for row in runtime_rows
        ),
        "runtime_product_rows": len(runtime_rows),
        "first_ebay_product_id": (
            ebay_batch[0].get("canonical_product_id", "")
            if ebay_batch else ""
        ),
        "last_ebay_product_id": (
            ebay_batch[-1].get("canonical_product_id", "")
            if ebay_batch else ""
        ),
        "ebay_batch_product_ids": [
            str(row.get("canonical_product_id") or "")
            for row in ebay_batch
        ],
    }
    return runtime_rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select a deterministic eBay batch while retaining full TCGCSV coverage."
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=DEFAULT_UNIVERSE,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_SUMMARY,
    )
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--run-number", type=int, default=1)
    parser.add_argument("--batch-index", type=int)
    args = parser.parse_args()

    fieldnames, rows = read_csv(args.universe.resolve())
    if "batch_role" not in fieldnames:
        fieldnames.append("batch_role")

    selected, summary = choose_batch(
        rows,
        batch_size=args.batch_size,
        run_number=args.run_number,
        requested_batch_index=args.batch_index,
    )
    write_csv(args.output.resolve(), fieldnames, selected)
    args.summary_output.resolve().parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.summary_output.resolve().write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
