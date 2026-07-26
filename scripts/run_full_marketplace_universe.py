from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "scripts" / "run_mtg_marketplace_production.py"
MAP_FIELDS = (
    "box_name", "tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id",
    "scryfall_set_code", "source_product_name", "source_url", "verified", "notes",
    "mapping_status", "investment_product_id", "investment_product_type",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...] | list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _batch_ranges(total: int, batch_size: int) -> list[tuple[int, int]]:
    return [(start, min(start + batch_size, total)) for start in range(0, total, batch_size)]


def run_full_universe(
    product_map: Path,
    model_input: Path,
    output_root: Path,
    *,
    live: bool,
    batch_size: int,
    start_batch: int,
    max_batches: int,
    ebay_limit: int,
) -> dict[str, Any]:
    rows = [row for row in _read_csv(product_map) if str(row.get("mapping_status") or "READY").upper() == "READY"]
    ranges = _batch_ranges(len(rows), batch_size)
    selected = ranges[start_batch:]
    if max_batches > 0:
        selected = selected[:max_batches]

    output_root.mkdir(parents=True, exist_ok=True)
    batch_root = output_root / "batches"
    batch_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_root / "checkpoint.json"
    previous = _load_json(checkpoint_path)
    completed_before = set(int(value) for value in previous.get("completed_batches", []))

    completed = set(completed_before)
    batch_summaries: list[dict[str, Any]] = []
    all_observations: list[dict[str, str]] = []
    failures: list[int] = []

    for batch_index, (start, end) in enumerate(ranges):
        if (start, end) not in selected or batch_index in completed_before:
            continue
        batch_dir = batch_root / f"batch_{batch_index:04d}"
        batch_map = batch_dir / "product_map.csv"
        _write_csv(batch_map, rows[start:end], MAP_FIELDS)
        summary_path = batch_dir / "latest.json"
        command = [
            sys.executable,
            str(ORCHESTRATOR),
            "--product-map", str(batch_map),
            "--model-input", str(model_input),
            "--ebay-limit", str(ebay_limit),
            "--output", str(summary_path),
        ]
        if live:
            command.append("--live")
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        summary = _load_json(summary_path)
        summary.update({
            "batch_index": batch_index,
            "batch_start": start,
            "batch_end": end,
            "batch_product_count": end - start,
            "exit_code": result.returncode,
        })
        batch_summaries.append(summary)
        if result.returncode != 0:
            failures.append(batch_index)
            break

        completed.add(batch_index)
        observations_path = batch_dir / "normalized_marketplace_observations.csv"
        if observations_path.is_file():
            all_observations.extend(_read_csv(observations_path))

        checkpoint = {
            "status": "IN_PROGRESS",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_ready_products": len(rows),
            "batch_size": batch_size,
            "total_batches": len(ranges),
            "completed_batches": sorted(completed),
            "next_batch": batch_index + 1,
            "failed_batches": failures,
        }
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")

    # Rehydrate observations from all completed batches so resumed runs produce a complete aggregate.
    all_observations = []
    for batch_index in sorted(completed):
        path = batch_root / f"batch_{batch_index:04d}" / "normalized_marketplace_observations.csv"
        if path.is_file():
            all_observations.extend(_read_csv(path))
    observation_fields = list(all_observations[0]) if all_observations else [
        "observed_at_utc", "source_name", "product_name", "tcgplayer_product_id",
        "market_price", "low_price", "median_price", "listing_count", "seller_count",
        "confidence", "source_status", "source_run_id",
    ]
    _write_csv(output_root / "normalized_marketplace_observations.csv", all_observations, observation_fields)

    all_complete = len(completed) == len(ranges)
    status = "PASS" if all_complete and not failures else "PARTIAL" if completed else "INCOMPLETE"
    payload = {
        "status": status,
        "mode": "LIVE" if live else "NON_LIVE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_ready_products": len(rows),
        "batch_size": batch_size,
        "total_batches": len(ranges),
        "completed_batch_count": len(completed),
        "completed_batches": sorted(completed),
        "failed_batches": failures,
        "normalized_observation_count": len(all_observations),
        "next_batch": next((index for index in range(len(ranges)) if index not in completed), None),
        "checkpoint_output": str(checkpoint_path.resolve()),
        "normalized_observations_output": str((output_root / "normalized_marketplace_observations.csv").resolve()),
        "batch_summaries": batch_summaries,
        "reason_codes": [
            "FULL_MARKETPLACE_UNIVERSE_COMPLETED" if status == "PASS" else
            "FULL_MARKETPLACE_UNIVERSE_PARTIAL" if status == "PARTIAL" else
            "FULL_MARKETPLACE_UNIVERSE_NOT_COMPLETED"
        ],
    }
    (output_root / "latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    checkpoint = {
        **payload,
        "status": status,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full MTG marketplace universe in resumable batches")
    parser.add_argument("--product-map", type=Path, required=True)
    parser.add_argument("--model-input", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--max-batches", type=int, default=0, help="0 processes all remaining batches")
    parser.add_argument("--ebay-limit", type=int, default=10)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if args.start_batch < 0:
        parser.error("--start-batch cannot be negative")
    if args.max_batches < 0:
        parser.error("--max-batches cannot be negative")
    if args.ebay_limit < 1 or args.ebay_limit > 200:
        parser.error("--ebay-limit must be between 1 and 200")
    if args.live and os.getenv("MTG_LIVE_EXECUTION", "false").lower() != "true":
        parser.error("live execution requires MTG_LIVE_EXECUTION=true")
    payload = run_full_universe(
        args.product_map.resolve(),
        args.model_input.resolve(),
        args.output_root.resolve(),
        live=args.live,
        batch_size=args.batch_size,
        start_batch=args.start_batch,
        max_batches=args.max_batches,
        ebay_limit=args.ebay_limit,
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] in {"PASS", "PARTIAL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
