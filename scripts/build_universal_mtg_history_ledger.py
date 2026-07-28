from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

FOUNDATION_HISTORY = (
    ROOT / "data/operations/mtg_history_foundation/"
    "universal_mtg_price_history.csv"
)
FOUNDATION_COVERAGE = (
    ROOT / "data/operations/mtg_history_foundation/"
    "universal_mtg_history_coverage.csv"
)
ARCHIVE_HISTORY = (
    ROOT / "data/operations/mtg_universal_history_completion/archive/"
    "universal_tcgcsv_monthly_archive_observations.csv"
)
ROUTING_MATRIX = (
    ROOT / "data/operations/mtg_universal_history_completion/"
    "universal_history_routing_matrix.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_universal_history_ledger"
)

RAW_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "tcgplayer_product_id", "source_name", "source_product_id",
    "observation_date", "observed_at_utc", "market_price", "low_price",
    "high_price", "listing_count", "seller_count", "currency",
    "price_field", "mapping_method", "source_file", "collection_run_id",
    "is_live_observation", "observation_fingerprint",
]

VERIFICATION_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "tcgplayer_product_id", "tcgcsv_identity_status",
    "tcgcsv_archive_eligible", "ebay_history_eligible",
    "distinct_history_dates", "first_history_date", "latest_history_date",
    "history_source_count", "history_sources",
    "history_verification_status", "history_completion_route",
    "live_history_accumulation_required", "source_exhaustion_status",
]


def load_daily_module():
    path = ROOT / "scripts" / "build_universal_mtg_daily_history.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_mtg_daily_history",
        path,
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    return str(value or "").strip()


def normalize_foundation(
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        normalized = {field: clean(row.get(field)) for field in RAW_FIELDS}
        if (
            not normalized["canonical_product_id"]
            or not normalized["source_name"]
            or not normalized["observation_date"]
            or not normalized["market_price"]
        ):
            continue
        output.append(normalized)
    return output


def normalize_archive(
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        product_id = clean(row.get("universal_mtg_product_id"))
        date = clean(row.get("observation_date"))[:10]
        price = clean(row.get("selected_price"))
        if not product_id or not date or not price:
            continue
        source_product_id = clean(row.get("tcgplayer_product_id"))
        fingerprint = (
            f"TCGCSV_ARCHIVE|{product_id}|{date}|"
            f"{clean(row.get('tcgcsv_category_id'))}|"
            f"{clean(row.get('tcgcsv_group_id'))}"
        )
        output.append({
            "canonical_product_id": product_id,
            "canonical_product_name": clean(
                row.get("canonical_product_name")
            ),
            "product_class": clean(row.get("product_class")),
            "tcgplayer_product_id": source_product_id,
            "source_name": "TCGCSV_ARCHIVE",
            "source_product_id": source_product_id,
            "observation_date": date,
            "observed_at_utc": clean(row.get("collected_at_utc")),
            "market_price": price,
            "low_price": clean(row.get("low_price")),
            "high_price": clean(row.get("high_price")),
            "listing_count": "",
            "seller_count": "",
            "currency": "USD",
            "price_field": "selected_price",
            "mapping_method": "GOVERNED_TCGCSV_ARCHIVE_ROUTE",
            "source_file": (
                "universal_tcgcsv_monthly_archive_observations.csv"
            ),
            "collection_run_id": clean(row.get("run_id")),
            "is_live_observation": "false",
            "observation_fingerprint": fingerprint,
        })
    return output


def dedupe_raw(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_fingerprint: dict[str, dict[str, Any]] = {}
    for row in rows:
        fingerprint = clean(row.get("observation_fingerprint"))
        if not fingerprint:
            fingerprint = "|".join([
                clean(row.get("canonical_product_id")),
                clean(row.get("source_name")),
                clean(row.get("observation_date"))[:10],
                clean(row.get("market_price")),
                clean(row.get("source_product_id")),
            ])
            row = dict(row)
            row["observation_fingerprint"] = fingerprint
        by_fingerprint[fingerprint] = row
    return sorted(
        by_fingerprint.values(),
        key=lambda row: (
            clean(row.get("canonical_product_id")),
            clean(row.get("observation_date")),
            clean(row.get("source_name")),
            clean(row.get("observation_fingerprint")),
        ),
    )


def history_status(date_count: int) -> str:
    if date_count >= 30:
        return "HISTORY_30_PLUS_DATES"
    if date_count >= 2:
        return "HISTORY_2_TO_29_DATES"
    if date_count == 1:
        return "HISTORY_1_DATE"
    return "NO_DIRECT_HISTORY"


def build_verification(
    routing_rows: list[dict[str, str]],
    consolidated_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in consolidated_rows:
        by_product[clean(row.get("canonical_product_id"))].append(row)

    output: list[dict[str, Any]] = []
    for route in routing_rows:
        product_id = clean(route.get("universal_mtg_product_id"))
        rows = by_product.get(product_id, [])
        dates = sorted({
            clean(row.get("observation_date"))
            for row in rows
            if clean(row.get("observation_date"))
        })
        sources: set[str] = set()
        for row in rows:
            sources.update(
                part for part in clean(row.get("source_names")).split("|")
                if part
            )
        status = history_status(len(dates))
        primary_route = clean(route.get("primary_history_route"))
        if status == "NO_DIRECT_HISTORY":
            if primary_route == "EBAY_DAILY_ACCUMULATION":
                completion_route = "EBAY_ACCUMULATION_REQUIRED"
            elif clean(route.get("tcgcsv_identity_status")) in {
                "TCGCSV_ID_AMBIGUOUS",
                "TCGCSV_ID_NOT_FOUND",
            }:
                completion_route = "IDENTITY_REVIEW_REQUIRED"
            else:
                completion_route = "ARCHIVE_HISTORY_NOT_AVAILABLE"
        else:
            completion_route = "DIRECT_HISTORY_AVAILABLE"

        output.append({
            "canonical_product_id": product_id,
            "canonical_product_name": clean(
                route.get("canonical_product_name")
            ),
            "product_class": clean(route.get("product_class")),
            "tcgplayer_product_id": clean(
                route.get("tcgplayer_product_id")
            ),
            "tcgcsv_identity_status": clean(
                route.get("tcgcsv_identity_status")
            ),
            "tcgcsv_archive_eligible": clean(
                route.get("tcgcsv_archive_eligible")
            ),
            "ebay_history_eligible": clean(
                route.get("ebay_history_eligible")
            ),
            "distinct_history_dates": len(dates),
            "first_history_date": dates[0] if dates else "",
            "latest_history_date": dates[-1] if dates else "",
            "history_source_count": len(sources),
            "history_sources": "|".join(sorted(sources)),
            "history_verification_status": status,
            "history_completion_route": completion_route,
            "live_history_accumulation_required": (
                "false" if len(dates) >= 30 else "true"
            ),
            "source_exhaustion_status": (
                "ARCHIVE_EXECUTED"
                if clean(route.get("tcgcsv_archive_eligible")) == "true"
                else "ARCHIVE_NOT_ELIGIBLE"
            ),
        })
    return sorted(output, key=lambda row: row["canonical_product_id"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the governed universal MTG historical ledger from "
            "existing direct history and universal TCGCSV archive history."
        )
    )
    parser.add_argument(
        "--foundation-history",
        type=Path,
        default=FOUNDATION_HISTORY,
    )
    parser.add_argument(
        "--foundation-coverage",
        type=Path,
        default=FOUNDATION_COVERAGE,
    )
    parser.add_argument(
        "--archive-history",
        type=Path,
        default=ARCHIVE_HISTORY,
    )
    parser.add_argument(
        "--routing-matrix",
        type=Path,
        default=ROUTING_MATRIX,
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    foundation = normalize_foundation(
        read_csv(args.foundation_history.resolve())
    )
    archive = normalize_archive(
        read_csv(args.archive_history.resolve())
    )
    routing = read_csv(args.routing_matrix.resolve())
    coverage = read_csv(args.foundation_coverage.resolve())

    if len(routing) != 1141:
        raise SystemExit(
            f"Expected 1,141 routing rows; found {len(routing)}."
        )
    if len(coverage) != 1141:
        raise SystemExit(
            f"Expected 1,141 coverage rows; found {len(coverage)}."
        )

    raw_ledger = dedupe_raw([*foundation, *archive])
    daily_module = load_daily_module()
    daily_source = daily_module.build_daily_source(raw_ledger)
    daily_consolidated = daily_module.build_daily_consolidated(daily_source)
    verification = build_verification(routing, daily_consolidated)

    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_mtg_historical_observation_ledger.csv",
        raw_ledger,
        RAW_FIELDS,
    )
    write_csv(
        output_root / "universal_mtg_daily_source_ledger.csv",
        daily_source,
        list(daily_source[0].keys()),
    )
    write_csv(
        output_root / "universal_mtg_daily_consolidated_ledger.csv",
        daily_consolidated,
        list(daily_consolidated[0].keys()),
    )
    write_csv(
        output_root / "universal_mtg_history_completion_status.csv",
        verification,
        VERIFICATION_FIELDS,
    )

    status_counts = Counter(
        row["history_verification_status"] for row in verification
    )
    route_counts = Counter(
        row["history_completion_route"] for row in verification
    )
    source_counts = Counter(
        row["source_name"] for row in daily_source
    )
    raw_keys = {
        (
            row["canonical_product_id"],
            row["source_name"],
            row["observation_date"],
            row["observation_fingerprint"],
        )
        for row in raw_ledger
    }
    daily_source_keys = {
        (
            row["canonical_product_id"],
            row["source_name"],
            row["observation_date"],
        )
        for row in daily_source
    }
    consolidated_keys = {
        (
            row["canonical_product_id"],
            row["observation_date"],
        )
        for row in daily_consolidated
    }

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governed_products": len(verification),
        "foundation_raw_rows": len(foundation),
        "archive_raw_rows": len(archive),
        "raw_ledger_rows": len(raw_ledger),
        "daily_source_rows": len(daily_source),
        "daily_consolidated_rows": len(daily_consolidated),
        "products_with_direct_history": sum(
            int(row["distinct_history_dates"]) > 0
            for row in verification
        ),
        "products_with_30_plus_dates": sum(
            int(row["distinct_history_dates"]) >= 30
            for row in verification
        ),
        "products_with_no_direct_history": sum(
            int(row["distinct_history_dates"]) == 0
            for row in verification
        ),
        "history_status_counts": dict(sorted(status_counts.items())),
        "history_completion_route_counts": dict(sorted(route_counts.items())),
        "daily_source_counts": dict(sorted(source_counts.items())),
        "certification_checks": {
            "verification_rows_equal_1141": len(verification) == 1141,
            "verification_product_ids_unique": len({
                row["canonical_product_id"] for row in verification
            }) == 1141,
            "raw_ledger_keys_unique": len(raw_ledger) == len(raw_keys),
            "daily_source_keys_unique": (
                len(daily_source) == len(daily_source_keys)
            ),
            "consolidated_product_dates_unique": (
                len(daily_consolidated) == len(consolidated_keys)
            ),
            "model_values_excluded_from_daily_history": all(
                clean(row.get("price_field"))
                not in daily_module.MODEL_FIELDS
                for row in raw_ledger
                if clean(row.get("source_name")) == "MODEL"
            ),
            "archive_rows_present": len(archive) == 21837,
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    (
        output_root / "universal_mtg_history_ledger_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
