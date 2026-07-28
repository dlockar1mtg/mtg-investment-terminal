from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ARCHIVE = (
    ROOT
    / "data"
    / "operations"
    / "mtg_tcgcsv_price_backfill"
    / "archive"
    / "tcgcsv_monthly_archive_observations.csv"
)

DEFAULT_CURRENT = (
    ROOT
    / "data"
    / "warehouse"
    / "current"
    / "secret_lair"
    / "master_secret_lair_price_history.csv"
)

DEFAULT_EVALUATION = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "ebay_matching"
    / "production_refresh"
    / "full_model_evaluation"
    / "secret_lair_full_model_evaluation.csv"
)

DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "validation"
    / "phase_8"
    / "secret_lair_history_recovery"
)

ID_ALIASES = (
    "secret_lair_id",
    "investment_product_id",
    "product_id",
    "canonical_product_id",
    "universal_mtg_product_id",
    "asset_id",
)

DATE_ALIASES = (
    "observation_date",
    "snapshot_date",
    "price_date",
    "as_of_date",
    "archive_date",
    "archive_month",
    "observed_at",
    "collected_at",
    "generated_at",
)

MARKET_PRICE_ALIASES = (
    "market_price",
    "market_price_usd",
    "tcg_market_price",
    "current_market_price",
    "current_market_value_usd",
    "price",
    "price_usd",
)

LOW_PRICE_ALIASES = (
    "low_price",
    "low_price_usd",
    "tcg_low_price",
    "lowest_price",
)

SOURCE_ALIASES = (
    "source_name",
    "source",
    "provider",
    "price_source",
)

RECORD_ID_ALIASES = (
    "source_record_id",
    "record_id",
    "listing_id",
    "observation_id",
)

CANONICAL_FIELDS = [
    "observation_date",
    "secret_lair_id",
    "source_name",
    "market_price",
    "low_price",
    "source_record_id",
    "source_file",
    "recovery_status",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def parse_date(value: Any) -> date | None:
    text = clean(value)
    if not text:
        return None

    candidates = [
        text[:10],
        text[:7] + "-01" if re.fullmatch(r"\d{4}-\d{2}", text[:7]) else "",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass

    # Common US formats.
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def normalize_id(value: Any) -> str:
    text = clean(value)
    for prefix in (
        "MTG:SECRET_LAIR:",
        "SECRET_LAIR:",
        "MTG-SECRET-LAIR-",
    ):
        if text.upper().startswith(prefix):
            return text[len(prefix):]
    return text


def first_present(row: dict[str, str], aliases: Iterable[str]) -> str:
    lowered = {key.lower(): key for key in row}
    for alias in aliases:
        actual = lowered.get(alias.lower())
        if actual is not None and clean(row.get(actual)):
            return clean(row.get(actual))
    return ""


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def governed_products(
    evaluation_path: Path,
) -> dict[str, dict[str, str]]:
    rows = read_csv(evaluation_path)
    products: dict[str, dict[str, str]] = {}
    for row in rows:
        product_id = normalize_id(
            first_present(row, ID_ALIASES)
        )
        if product_id:
            products[product_id] = row
    if len(products) != 973:
        raise RuntimeError(
            "Expected 973 governed Secret Lair products; "
            f"found {len(products)}"
        )
    return products


def normalize_source_rows(
    rows: list[dict[str, str]],
    source_file: Path,
    governed: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=2):
        product_id = normalize_id(first_present(row, ID_ALIASES))
        observed = parse_date(first_present(row, DATE_ALIASES))
        market = number(first_present(row, MARKET_PRICE_ALIASES))
        low = number(first_present(row, LOW_PRICE_ALIASES))
        source = first_present(row, SOURCE_ALIASES) or source_file.stem
        record_id = (
            first_present(row, RECORD_ID_ALIASES)
            or f"{source_file.name}:{index}"
        )

        reasons: list[str] = []
        if not product_id:
            reasons.append("MISSING_PRODUCT_ID")
        elif product_id not in governed:
            reasons.append("UNGOVERNED_PRODUCT_ID")
        if observed is None:
            reasons.append("INVALID_OR_MISSING_DATE")
        if not (
            (market is not None and market > 0)
            or (low is not None and low > 0)
        ):
            reasons.append("NO_POSITIVE_PRICE")

        normalized = {
            "observation_date": (
                observed.isoformat() if observed else ""
            ),
            "secret_lair_id": product_id,
            "source_name": source,
            "market_price": (
                round(market, 2)
                if market is not None and market > 0
                else ""
            ),
            "low_price": (
                round(low, 2)
                if low is not None and low > 0
                else ""
            ),
            "source_record_id": record_id,
            "source_file": str(source_file.relative_to(ROOT)),
            "recovery_status": "VALID" if not reasons else "|".join(reasons),
        }

        if reasons:
            rejected.append(normalized)
        else:
            valid.append(normalized)

    return valid, rejected


def deduplicate(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[
        tuple[str, str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in rows:
        key = (
            clean(row["secret_lair_id"]),
            clean(row["observation_date"]),
            clean(row["source_name"]).upper(),
        )
        grouped[key].append(row)

    output: list[dict[str, Any]] = []
    for key, records in grouped.items():
        markets = [
            number(record["market_price"])
            for record in records
            if number(record["market_price"]) is not None
        ]
        lows = [
            number(record["low_price"])
            for record in records
            if number(record["low_price"]) is not None
        ]
        record_ids = sorted(
            {
                clean(record["source_record_id"])
                for record in records
                if clean(record["source_record_id"])
            }
        )
        files = sorted(
            {
                clean(record["source_file"])
                for record in records
                if clean(record["source_file"])
            }
        )
        output.append(
            {
                "observation_date": key[1],
                "secret_lair_id": key[0],
                "source_name": key[2],
                "market_price": (
                    round(float(median(markets)), 2)
                    if markets else ""
                ),
                "low_price": (
                    round(float(median(lows)), 2)
                    if lows else ""
                ),
                "source_record_id": "|".join(record_ids),
                "source_file": "|".join(files),
                "recovery_status": "RECOVERED_CANONICAL",
            }
        )

    output.sort(
        key=lambda row: (
            row["secret_lair_id"],
            row["observation_date"],
            row["source_name"],
        )
    )
    return output


def coverage_rows(
    canonical: list[dict[str, Any]],
    governed: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canonical:
        by_product[clean(row["secret_lair_id"])].append(row)

    output: list[dict[str, Any]] = []
    for product_id, product in governed.items():
        rows = by_product.get(product_id, [])
        dates = sorted(
            {
                clean(row["observation_date"])
                for row in rows
                if clean(row["observation_date"])
            }
        )
        sources = sorted(
            {
                clean(row["source_name"])
                for row in rows
                if clean(row["source_name"])
            }
        )
        output.append(
            {
                "investment_product_id": product_id,
                "canonical_product_name": clean(
                    product.get("canonical_product_name")
                ),
                "observation_rows": len(rows),
                "distinct_dates": len(dates),
                "earliest_date": dates[0] if dates else "",
                "latest_date": dates[-1] if dates else "",
                "elapsed_days": (
                    (
                        date.fromisoformat(dates[-1])
                        - date.fromisoformat(dates[0])
                    ).days
                    if len(dates) >= 2
                    else 0
                ),
                "source_count": len(sources),
                "sources": "|".join(sources),
                "history_eligible_30d": (
                    "YES"
                    if len(dates) >= 2
                    and (
                        date.fromisoformat(dates[-1])
                        - date.fromisoformat(dates[0])
                    ).days >= 30
                    else "NO"
                ),
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument(
        "--evaluation",
        type=Path,
        default=DEFAULT_EVALUATION,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    if not args.archive.is_file():
        raise FileNotFoundError(
            "The longitudinal archive was not found: "
            f"{args.archive}"
        )
    if not args.current.is_file():
        raise FileNotFoundError(
            f"Current snapshot was not found: {args.current}"
        )

    governed = governed_products(args.evaluation)
    governed_ids = set(governed)

    archive_raw = read_csv(args.archive)
    current_raw = read_csv(args.current)

    archive_valid, archive_rejected = normalize_source_rows(
        archive_raw,
        args.archive,
        governed_ids,
    )
    current_valid, current_rejected = normalize_source_rows(
        current_raw,
        args.current,
        governed_ids,
    )

    canonical = deduplicate(archive_valid + current_valid)
    coverage = coverage_rows(canonical, governed)

    multi_date = [
        row for row in coverage
        if int(row["distinct_dates"]) >= 2
    ]
    eligible = [
        row for row in coverage
        if row["history_eligible_30d"] == "YES"
    ]
    dated_products = [
        row for row in coverage
        if int(row["distinct_dates"]) >= 1
    ]

    canonical_keys = {
        (
            row["secret_lair_id"],
            row["observation_date"],
            row["source_name"],
        )
        for row in canonical
    }
    current_keys = {
        (
            row["secret_lair_id"],
            row["observation_date"],
            clean(row["source_name"]).upper(),
        )
        for row in current_valid
    }

    checks = {
        "governed_products_equal_973": len(governed) == 973,
        "archive_rows_loaded": len(archive_raw) > 0,
        "archive_valid_rows_found": len(archive_valid) > 0,
        "archive_has_multiple_dates": len(
            {
                row["observation_date"]
                for row in archive_valid
            }
        ) >= 2,
        "current_snapshot_preserved": current_keys <= canonical_keys,
        "canonical_rows_not_less_than_current": (
            len(canonical) >= len(current_valid)
        ),
        "multi_date_products_found": len(multi_date) > 0,
        "thirty_day_history_products_found": len(eligible) > 0,
        "canonical_ids_governed": all(
            row["secret_lair_id"] in governed_ids
            for row in canonical
        ),
    }

    status = "CERTIFIED" if all(checks.values()) else "FAILED"

    args.output_root.mkdir(parents=True, exist_ok=True)

    canonical_path = (
        args.output_root
        / "candidate_master_secret_lair_price_history.csv"
    )
    coverage_path = (
        args.output_root
        / "secret_lair_longitudinal_coverage.csv"
    )
    rejected_path = (
        args.output_root
        / "secret_lair_rejected_history_rows.csv"
    )

    write_csv(canonical_path, canonical, CANONICAL_FIELDS)
    write_csv(
        coverage_path,
        coverage,
        [
            "investment_product_id",
            "canonical_product_name",
            "observation_rows",
            "distinct_dates",
            "earliest_date",
            "latest_date",
            "elapsed_days",
            "source_count",
            "sources",
            "history_eligible_30d",
        ],
    )
    write_csv(
        rejected_path,
        archive_rejected + current_rejected,
        CANONICAL_FIELDS,
    )

    all_dates = sorted(
        {
            row["observation_date"]
            for row in canonical
            if clean(row["observation_date"])
        }
    )

    manifest = {
        "status": status,
        "phase": "8.2.1D.3",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "archive": {
                "path": str(args.archive),
                "sha256": sha256(args.archive),
                "raw_rows": len(archive_raw),
                "valid_rows": len(archive_valid),
                "rejected_rows": len(archive_rejected),
            },
            "current": {
                "path": str(args.current),
                "sha256": sha256(args.current),
                "raw_rows": len(current_raw),
                "valid_rows": len(current_valid),
                "rejected_rows": len(current_rejected),
            },
        },
        "coverage": {
            "canonical_rows": len(canonical),
            "governed_products": len(governed),
            "products_with_any_history": len(dated_products),
            "products_with_multiple_dates": len(multi_date),
            "products_with_at_least_30_days": len(eligible),
            "distinct_dates": len(all_dates),
            "earliest_date": all_dates[0] if all_dates else "",
            "latest_date": all_dates[-1] if all_dates else "",
        },
        "checks": checks,
        "outputs": {
            "candidate_history": str(canonical_path),
            "coverage": str(coverage_path),
            "rejected": str(rejected_path),
        },
    }

    manifest_path = (
        args.output_root
        / "PHASE_8_2_1D_3_HISTORY_RECOVERY_MANIFEST.json"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("PHASE 8.2.1D.3 — SECRET LAIR LONGITUDINAL HISTORY RECOVERY")
    print("=" * 78)
    print(f"Archive raw rows: {len(archive_raw)}")
    print(f"Archive valid rows: {len(archive_valid)}")
    print(f"Current valid rows: {len(current_valid)}")
    print(f"Canonical rows: {len(canonical)}")
    print(f"Products with any history: {len(dated_products)}")
    print(f"Products with multiple dates: {len(multi_date)}")
    print(f"Products with at least 30 days: {len(eligible)}")
    print(f"Distinct dates: {len(all_dates)}")
    if all_dates:
        print(f"Date coverage: {all_dates[0]} through {all_dates[-1]}")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} | {name}")
    print(f"Status: {status}")
    print(f"Candidate history: {canonical_path}")
    print(f"Manifest: {manifest_path}")
    print(f"PHASE 8.2.1D.3 HISTORY RECOVERY: {status}")

    return 0 if status == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
