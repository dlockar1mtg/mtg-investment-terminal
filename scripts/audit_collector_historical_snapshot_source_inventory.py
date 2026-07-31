from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data" / "operations" / "collector_backtest_source_inventory" / "candidate_v1_0_0"

SCAN_ROOTS = [
    ROOT / "data",
    ROOT / "config",
]

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "candidate_v1_0_0",
    "collector_backtest_source_inventory",
}

IDENTITY_FIELDS = {
    "investment_product_id",
    "source_product_id",
    "product_id",
    "asset_id",
    "tcgplayer_product_id",
}

TIME_FIELDS = {
    "date",
    "price_date",
    "current_price_date",
    "observation_date",
    "snapshot_date",
    "decision_date",
    "as_of_date",
    "release_date",
    "timestamp",
    "generated_at",
    "generated_at_utc",
}

PRICE_FIELDS = {
    "price",
    "market_price",
    "current_price",
    "low_price",
    "mid_price",
    "high_price",
    "value",
}

ROLE_KEYWORDS = {
    "PRICE_HISTORY": {"price", "history", "timeseries", "market"},
    "IDENTITY": {"registry", "identity", "product_master", "asset_master"},
    "EVIDENCE": {"evidence", "supply", "demand", "liquidity", "reprint"},
    "ROUTING": {"route", "routing", "forecast_method"},
    "COMPARABLES": {"comparable", "peer", "similarity"},
    "OUTCOMES": {"outcome", "return", "performance", "realized"},
}


def clean(value: object) -> str:
    return str(value or "").strip()


def classify_role(path: Path, fields: set[str]) -> str:
    searchable = f"{path.as_posix().lower()} {' '.join(sorted(fields))}"
    scores: dict[str, int] = {}
    for role, keywords in ROLE_KEYWORDS.items():
        scores[role] = sum(1 for keyword in keywords if keyword in searchable)
    best_role, best_score = max(scores.items(), key=lambda item: item[1])
    return best_role if best_score else "UNCLASSIFIED"


def inspect_csv(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = [clean(field) for field in (reader.fieldnames or []) if clean(field)]
            row_count = sum(1 for _ in reader)
    except Exception as exc:  # pragma: no cover - diagnostic path
        return {
            "read_status": "ERROR",
            "read_issue": f"{type(exc).__name__}: {exc}",
            "row_count": "",
            "field_count": "",
            "fields": "",
            "role": "UNCLASSIFIED",
            "identity_fields": "",
            "time_fields": "",
            "price_fields": "",
            "supports_identity_join": False,
            "supports_as_of_join": False,
            "supports_price_history": False,
            "snapshot_readiness": "UNREADABLE",
        }

    normalized = {field.lower() for field in fields}
    identity = sorted(normalized & IDENTITY_FIELDS)
    times = sorted(normalized & TIME_FIELDS)
    prices = sorted(normalized & PRICE_FIELDS)
    role = classify_role(path, normalized)
    supports_identity = bool(identity)
    supports_as_of = bool(times)
    supports_price_history = bool(identity and times and prices)

    if supports_price_history:
        readiness = "READY_FOR_PRICE_AS_OF_JOIN"
    elif supports_identity and supports_as_of:
        readiness = "READY_FOR_NONPRICE_AS_OF_JOIN"
    elif supports_identity:
        readiness = "IDENTITY_ONLY_NO_TIME_KEY"
    elif supports_as_of:
        readiness = "TIME_KEY_ONLY_NO_IDENTITY"
    else:
        readiness = "NOT_READY"

    return {
        "read_status": "PASS",
        "read_issue": "",
        "row_count": row_count,
        "field_count": len(fields),
        "fields": "|".join(fields),
        "role": role,
        "identity_fields": "|".join(identity),
        "time_fields": "|".join(times),
        "price_fields": "|".join(prices),
        "supports_identity_join": supports_identity,
        "supports_as_of_join": supports_as_of,
        "supports_price_history": supports_price_history,
        "snapshot_readiness": readiness,
    }


def candidate_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "path",
        "size_bytes",
        "modified_at_utc",
        "read_status",
        "read_issue",
        "row_count",
        "field_count",
        "fields",
        "role",
        "identity_fields",
        "time_fields",
        "price_fields",
        "supports_identity_join",
        "supports_as_of_join",
        "supports_price_history",
        "snapshot_readiness",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory repository CSV sources for time-correct Collector historical snapshots."
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for path in candidate_files():
        stat = path.stat()
        inspected = inspect_csv(path)
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "size_bytes": stat.st_size,
                "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                **inspected,
            }
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    inventory_path = OUTPUT_ROOT / "collector_historical_snapshot_source_inventory.csv"
    write_csv(inventory_path, rows)

    role_counts = Counter(clean(row["role"]) for row in rows)
    readiness_counts = Counter(clean(row["snapshot_readiness"]) for row in rows)
    unreadable = [row for row in rows if row["read_status"] != "PASS"]
    price_ready = [row for row in rows if row["supports_price_history"] is True]
    as_of_ready = [row for row in rows if row["supports_as_of_join"] is True]

    required_roles = {"PRICE_HISTORY", "IDENTITY", "EVIDENCE", "ROUTING", "COMPARABLES"}
    discovered_roles = {role for role, count in role_counts.items() if count > 0}
    missing_required_roles = sorted(required_roles - discovered_roles)

    summary = {
        "audit_name": "Collector Historical Snapshot Source Inventory",
        "audit_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_note": (
            "This inventory identifies candidate historical sources and temporal join readiness only. "
            "It does not approve present-day data as historical evidence or run a backtest."
        ),
        "candidate_file_count": len(rows),
        "readable_file_count": len(rows) - len(unreadable),
        "unreadable_file_count": len(unreadable),
        "as_of_join_ready_file_count": len(as_of_ready),
        "price_history_ready_file_count": len(price_ready),
        "role_distribution": dict(sorted(role_counts.items())),
        "readiness_distribution": dict(sorted(readiness_counts.items())),
        "missing_required_roles": missing_required_roles,
        "historical_snapshot_builder_authorized": False,
        "future_information_prohibited": True,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS" if not unreadable else "REVIEW_REQUIRED",
    }

    summary_path = OUTPUT_ROOT / "collector_historical_snapshot_source_inventory_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    review_rows = [
        row
        for row in rows
        if row["snapshot_readiness"] not in {
            "READY_FOR_PRICE_AS_OF_JOIN",
            "READY_FOR_NONPRICE_AS_OF_JOIN",
        }
    ]
    write_csv(OUTPUT_ROOT / "collector_historical_snapshot_source_review_required.csv", review_rows)

    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and unreadable:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
