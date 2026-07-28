from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.universal_market_valuation import choose_valuation

HISTORY = (
    ROOT / "data/operations/mtg_universal_history_ledger/"
    "universal_mtg_daily_consolidated_ledger.csv"
)
STATUS = (
    ROOT / "data/operations/mtg_universal_history_ledger/"
    "universal_mtg_history_completion_status.csv"
)
ASKING = (
    ROOT / "data/operations/mtg_current_market_accumulation/"
    "universal_mtg_current_asking_history.csv"
)
OUTPUT = ROOT / "data/operations/mtg_universal_market_valuation"

VALUATION_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "selected_reference_price", "selected_reference_date",
    "selected_source_type", "valuation_state", "model_eligible",
    "dashboard_eligible", "freshness_days", "freshness_state",
    "valuation_reason", "historical_price", "historical_date",
    "historical_sources", "historical_distinct_dates",
    "current_asking_median", "current_asking_date",
    "current_asking_listing_count", "currency",
]
PROVENANCE_FIELDS = [
    "canonical_product_id", "selected_source_type", "selected_reference_date",
    "selected_reference_price", "historical_sources",
    "current_asking_attempt_id", "current_asking_fingerprint",
    "model_eligible", "dashboard_eligible", "valuation_reason",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def latest_by_product(
    rows: list[dict[str, str]],
    date_field: str = "observation_date",
) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        product_id = row.get("canonical_product_id", "").strip()
        if not product_id:
            continue
        current = latest.get(product_id)
        if current is None or row.get(date_field, "") > current.get(date_field, ""):
            latest[product_id] = row
    return latest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build one governed market-valuation row for all MTG products."
    )
    parser.add_argument("--history", type=Path, default=HISTORY)
    parser.add_argument("--status", type=Path, default=STATUS)
    parser.add_argument("--asking", type=Path, default=ASKING)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of_date)
    status_rows = read_csv(args.status.resolve())
    if len(status_rows) != 1141:
        raise SystemExit(
            f"Expected 1,141 governed status rows; found {len(status_rows)}."
        )

    history = latest_by_product(read_csv(args.history.resolve()))
    asking = latest_by_product(read_csv(args.asking.resolve()))

    valuations: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []

    for status in status_rows:
        product_id = status["canonical_product_id"]
        historical = history.get(product_id)
        current = asking.get(product_id)
        decision = choose_valuation(historical, current, as_of)

        row = {
            "canonical_product_id": product_id,
            "canonical_product_name": status.get("canonical_product_name", ""),
            "product_class": status.get("product_class", ""),
            "selected_reference_price": (
                "" if decision.selected_reference_price is None
                else round(decision.selected_reference_price, 4)
            ),
            "selected_reference_date": decision.selected_reference_date,
            "selected_source_type": decision.selected_source_type,
            "valuation_state": decision.valuation_state,
            "model_eligible": str(decision.model_eligible).lower(),
            "dashboard_eligible": str(decision.dashboard_eligible).lower(),
            "freshness_days": (
                "" if decision.freshness_days is None
                else decision.freshness_days
            ),
            "freshness_state": decision.freshness_state,
            "valuation_reason": decision.valuation_reason,
            "historical_price": (
                historical.get("consolidated_market_price", "")
                if historical else ""
            ),
            "historical_date": (
                historical.get("observation_date", "") if historical else ""
            ),
            "historical_sources": (
                historical.get("source_names", "") if historical else ""
            ),
            "historical_distinct_dates": status.get("distinct_history_dates", "0"),
            "current_asking_median": (
                current.get("median_price", "") if current else ""
            ),
            "current_asking_date": (
                current.get("observation_date", "") if current else ""
            ),
            "current_asking_listing_count": (
                current.get("listing_count", "") if current else ""
            ),
            "currency": "USD" if decision.selected_reference_price else "",
        }
        valuations.append(row)
        provenance.append({
            "canonical_product_id": product_id,
            "selected_source_type": decision.selected_source_type,
            "selected_reference_date": decision.selected_reference_date,
            "selected_reference_price": row["selected_reference_price"],
            "historical_sources": row["historical_sources"],
            "current_asking_attempt_id": (
                current.get("attempt_id", "") if current else ""
            ),
            "current_asking_fingerprint": (
                current.get("observation_fingerprint", "") if current else ""
            ),
            "model_eligible": row["model_eligible"],
            "dashboard_eligible": row["dashboard_eligible"],
            "valuation_reason": row["valuation_reason"],
        })

    valuations.sort(key=lambda row: row["canonical_product_id"])
    provenance.sort(key=lambda row: row["canonical_product_id"])
    gaps = [
        row for row in valuations
        if row["valuation_state"] == "VALUATION_UNAVAILABLE"
    ]
    dashboard = [
        row for row in valuations
        if row["dashboard_eligible"] == "true"
    ]
    model = [
        row for row in valuations
        if row["model_eligible"] == "true"
    ]

    output = args.output_root.resolve()
    write_csv(
        output / "universal_mtg_market_valuation.csv",
        valuations,
        VALUATION_FIELDS,
    )
    write_csv(
        output / "universal_mtg_market_provenance.csv",
        provenance,
        PROVENANCE_FIELDS,
    )
    write_csv(
        output / "universal_mtg_dashboard_market_dataset.csv",
        dashboard,
        VALUATION_FIELDS,
    )
    write_csv(
        output / "universal_mtg_model_eligible_market_dataset.csv",
        model,
        VALUATION_FIELDS,
    )
    write_csv(
        output / "universal_mtg_valuation_gap_queue.csv",
        gaps,
        VALUATION_FIELDS,
    )

    state_counts = Counter(row["valuation_state"] for row in valuations)
    source_counts = Counter(row["selected_source_type"] for row in valuations)
    checks = {
        "valuation_rows_equal_1141": len(valuations) == 1141,
        "canonical_product_ids_unique": (
            len({row["canonical_product_id"] for row in valuations}) == 1141
        ),
        "asking_reference_never_model_eligible": all(
            row["model_eligible"] == "false"
            for row in valuations
            if row["selected_source_type"] == "CURRENT_ASKING_REFERENCE"
        ),
        "unavailable_rows_have_no_price": all(
            row["selected_reference_price"] == ""
            for row in valuations
            if row["valuation_state"] == "VALUATION_UNAVAILABLE"
        ),
        "all_priced_rows_usd": all(
            row["currency"] == "USD"
            for row in valuations
            if row["selected_reference_price"] != ""
        ),
    }
    summary = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": args.as_of_date,
        "governed_products": len(valuations),
        "valuation_state_counts": dict(state_counts),
        "selected_source_counts": dict(source_counts),
        "dashboard_eligible_products": len(dashboard),
        "model_eligible_products": len(model),
        "valuation_unavailable_products": len(gaps),
        "certification_checks": checks,
    }
    (output / "universal_mtg_market_valuation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
