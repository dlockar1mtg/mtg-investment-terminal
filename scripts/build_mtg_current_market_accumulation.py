from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ATTEMPTS = (
    ROOT / "data/operations/mtg_universal_history_production/"
    "current_market/attempts"
)
OUTPUT = ROOT / "data/operations/mtg_current_market_accumulation"

from terminal2.market_sources.current_market_quality import (
    evaluate_identity,
    robust_snapshot,
)

QUALITY_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "item_id", "title", "price", "currency", "classification",
    "identity_score", "matched_tokens", "required_tokens",
    "quality_state", "quality_reason", "attempt_id", "observation_date",
]
SNAPSHOT_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "observation_date", "source_name", "listing_count", "minimum_price",
    "median_price", "maximum_price", "currency", "quality_state",
    "attempt_id", "observation_fingerprint",
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

def latest_complete_attempt() -> Path:
    candidates = sorted(
        path for path in ATTEMPTS.glob("attempt_*")
        if (path / "attempt_summary.json").is_file()
        and (path / "current_market_listings.csv").is_file()
    )
    if not candidates:
        raise SystemExit("No completed current-market attempt found.")
    for path in reversed(candidates):
        summary = json.loads(
            (path / "attempt_summary.json").read_text(encoding="utf-8")
        )
        if summary.get("status") == "PASS":
            return path
    raise SystemExit("No PASS current-market attempt found.")

def dedupe_append(
    path: Path,
    new_rows: list[dict[str, Any]],
    fields: list[str],
    key_field: str,
) -> list[dict[str, Any]]:
    existing = read_csv(path) if path.is_file() else []
    combined = {
        str(row.get(key_field, "")): row
        for row in [*existing, *new_rows]
        if str(row.get(key_field, ""))
    }
    rows = [combined[key] for key in sorted(combined)]
    write_csv(path, rows, fields)
    return rows

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    attempt = (
        args.attempt_root.resolve()
        if args.attempt_root
        else latest_complete_attempt()
    )
    attempt_id = attempt.name
    summary = json.loads(
        (attempt / "attempt_summary.json").read_text(encoding="utf-8")
    )
    observation_date = str(summary["generated_at_utc"])[:10]
    rows = read_csv(attempt / "current_market_listings.csv")

    quality_rows: list[dict[str, Any]] = []
    approved_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        if row.get("accepted") != "true":
            continue
        decision = evaluate_identity(
            row.get("canonical_product_name", ""),
            row.get("title", ""),
        )
        quality = {
            **row,
            "identity_score": decision.identity_score,
            "matched_tokens": "|".join(decision.matched_tokens),
            "required_tokens": "|".join(decision.required_tokens),
            "quality_state": decision.quality_state,
            "quality_reason": decision.quality_reason,
            "attempt_id": attempt_id,
            "observation_date": observation_date,
        }
        quality_rows.append(quality)
        if decision.quality_state == "AUTO_APPROVED":
            approved_by_product[row["canonical_product_id"]].append(quality)

    snapshots: list[dict[str, Any]] = []
    for product_id, group in approved_by_product.items():
        prices = [float(row["price"]) for row in group]
        metric = robust_snapshot(prices)
        first = group[0]
        snapshots.append({
            "canonical_product_id": product_id,
            "canonical_product_name": first["canonical_product_name"],
            "product_class": first["product_class"],
            "observation_date": observation_date,
            "source_name": "EBAY_CURRENT_ASKING",
            **metric,
            "currency": "USD",
            "quality_state": "AUTO_APPROVED",
            "attempt_id": attempt_id,
            "observation_fingerprint": (
                f"EBAY_CURRENT_ASKING|{product_id}|{observation_date}"
            ),
        })

    output = args.output_root.resolve()
    write_csv(
        output / "latest_listing_quality_review.csv",
        quality_rows,
        QUALITY_FIELDS,
    )
    write_csv(
        output / "latest_current_market_snapshot.csv",
        snapshots,
        SNAPSHOT_FIELDS,
    )
    history = dedupe_append(
        output / "universal_mtg_current_asking_history.csv",
        snapshots,
        SNAPSHOT_FIELDS,
        "observation_fingerprint",
    )
    review = [
        row for row in quality_rows
        if row["quality_state"] != "AUTO_APPROVED"
    ]
    write_csv(
        output / "current_market_manual_review_queue.csv",
        review,
        QUALITY_FIELDS,
    )

    counts = Counter(row["quality_state"] for row in quality_rows)
    result = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_attempt": str(attempt),
        "accepted_input_listings": len(quality_rows),
        "quality_state_counts": dict(counts),
        "auto_approved_products": len(snapshots),
        "manual_review_listings": len(review),
        "persistent_snapshot_rows": len(history),
        "current_market_is_sold_history": False,
    }
    (output / "current_market_accumulation_summary.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
