from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


EXPECTED_CANONICAL_COUNT = 186
EXPECTED_ADMITTED_PRODUCTS = 115
EXPECTED_GAP_PRODUCTS = 71
EXPECTED_HISTORY_ROWS = 3390
EXPECTED_DISTINCT_DATES = 30
EXPECTED_IDENTITY_SHA = (
    "e75151ab05e87c60559e3114b050717307678f4ed0da01f067de46474a7ed4ac"
)

HISTORY_FIELDS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "product_name",
    "observation_date",
    "historical_price",
    "historical_source",
    "source_file_sha256",
]

COVERAGE_FIELDS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "product_name",
    "historical_evidence_status",
    "historical_source",
    "observation_count",
    "distinct_date_count",
    "first_observation_date",
    "last_observation_date",
    "model_eligibility_automatically_changed",
]

GAP_FIELDS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "product_name",
    "historical_evidence_status",
    "gap_reason",
    "canonical_universe_membership",
    "model_exclusion_authorized",
    "synthetic_price_authorized",
]


def fail(message: str) -> None:
    raise RuntimeError(f"FAIL-CLOSED: {message}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
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


def normalize_tcg_id(value: object) -> str:
    text = str(value or "").strip()
    if text.casefold().startswith("tcgplayer:"):
        text = text.split(":", 1)[1]
    if text.endswith(".0"):
        text = text[:-2]
    return text.strip()


def normalize_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    # Certified source already uses ISO-style dates.
    date_part = text[:10]

    try:
        datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return ""

    return date_part


def normalize_price(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    try:
        price = Decimal(text)
    except InvalidOperation:
        return ""

    if price <= 0:
        return ""

    normalized = format(price.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")

    return normalized


def read_stage9_universe(
    package: Path,
) -> list[dict[str, str]]:
    with zipfile.ZipFile(package, "r") as archive:
        member = "precollector_canonical_universe.csv"

        if member not in archive.namelist():
            fail(f"missing Stage 9 member: {member}")

        raw = archive.read(member).decode("utf-8-sig")
        return list(csv.DictReader(raw.splitlines()))


def build_authority(
    stage9_package: Path,
    archive_path: Path,
    output_root: Path,
) -> dict[str, object]:
    canonical_rows = read_stage9_universe(stage9_package)

    if len(canonical_rows) != EXPECTED_CANONICAL_COUNT:
        fail(
            "canonical count mismatch: "
            f"{len(canonical_rows)} != {EXPECTED_CANONICAL_COUNT}"
        )

    canonical_by_tcg: dict[str, dict[str, str]] = {}

    for row in canonical_rows:
        canonical_id = str(row.get("canonical_product_id") or "").strip()
        tcg_id = normalize_tcg_id(canonical_id)

        if not tcg_id:
            fail("blank canonical TCGplayer identity")

        if tcg_id in canonical_by_tcg:
            fail(f"duplicate canonical TCGplayer identity: {tcg_id}")

        canonical_by_tcg[tcg_id] = {
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": tcg_id,
            "product_name": str(row.get("product_name") or "").strip(),
        }

    source_sha = sha256_file(archive_path)
    source_rows = read_csv(archive_path)

    admitted_rows: list[dict[str, object]] = []
    prices_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in source_rows:
        tcg_id = normalize_tcg_id(row.get("tcgplayer_product_id"))

        if tcg_id not in canonical_by_tcg:
            continue

        observation_date = normalize_date(row.get("observation_date"))
        selected_price = normalize_price(row.get("selected_price"))

        if not observation_date or not selected_price:
            continue

        identity = canonical_by_tcg[tcg_id]
        key = (tcg_id, observation_date)

        prices_by_key[key].add(selected_price)

        admitted_rows.append(
            {
                "canonical_product_id": identity["canonical_product_id"],
                "tcgplayer_product_id": tcg_id,
                "product_name": identity["product_name"],
                "observation_date": observation_date,
                "historical_price": selected_price,
                "historical_source": "TCGCSV_ARCHIVE_MONTHLY_DIRECT",
                "source_file_sha256": source_sha,
            }
        )

    conflict_keys = sorted(
        key
        for key, prices in prices_by_key.items()
        if len(prices) > 1
    )

    if conflict_keys:
        fail(
            "direct TCGCSV archive contains conflicting "
            f"product/date prices: {len(conflict_keys)}"
        )

    # A direct authority must contain one row per product/date.
    unique_rows: dict[tuple[str, str], dict[str, object]] = {}

    for row in admitted_rows:
        key = (
            str(row["tcgplayer_product_id"]),
            str(row["observation_date"]),
        )

        if key in unique_rows:
            fail(f"duplicate direct product/date row: {key}")

        unique_rows[key] = row

    admitted_rows = sorted(
        unique_rows.values(),
        key=lambda row: (
            int(str(row["tcgplayer_product_id"])),
            str(row["observation_date"]),
        ),
    )

    product_rows: dict[str, list[dict[str, object]]] = defaultdict(list)

    for row in admitted_rows:
        product_rows[str(row["tcgplayer_product_id"])].append(row)

    admitted_products = set(product_rows)
    gap_products = set(canonical_by_tcg) - admitted_products

    distinct_dates = sorted(
        {
            str(row["observation_date"])
            for row in admitted_rows
        }
    )

    if len(admitted_products) != EXPECTED_ADMITTED_PRODUCTS:
        fail(
            "admitted product-count mismatch: "
            f"{len(admitted_products)} != {EXPECTED_ADMITTED_PRODUCTS}"
        )

    if len(gap_products) != EXPECTED_GAP_PRODUCTS:
        fail(
            "historical gap-count mismatch: "
            f"{len(gap_products)} != {EXPECTED_GAP_PRODUCTS}"
        )

    if len(admitted_rows) != EXPECTED_HISTORY_ROWS:
        fail(
            "historical row-count mismatch: "
            f"{len(admitted_rows)} != {EXPECTED_HISTORY_ROWS}"
        )

    if len(distinct_dates) != EXPECTED_DISTINCT_DATES:
        fail(
            "distinct-date mismatch: "
            f"{len(distinct_dates)} != {EXPECTED_DISTINCT_DATES}"
        )

    coverage_rows: list[dict[str, object]] = []
    gap_rows: list[dict[str, object]] = []

    for tcg_id in sorted(canonical_by_tcg, key=int):
        identity = canonical_by_tcg[tcg_id]
        rows = product_rows.get(tcg_id, [])

        if rows:
            product_dates = sorted(
                {
                    str(row["observation_date"])
                    for row in rows
                }
            )

            if len(product_dates) < 2:
                fail(
                    "admitted product has fewer than two distinct dates: "
                    f"{tcg_id}"
                )

            coverage_rows.append(
                {
                    "canonical_product_id":
                        identity["canonical_product_id"],
                    "tcgplayer_product_id": tcg_id,
                    "product_name": identity["product_name"],
                    "historical_evidence_status":
                        "CERTIFIED_TCGCSV_MONTHLY_HISTORY",
                    "historical_source":
                        "TCGCSV_ARCHIVE_MONTHLY_DIRECT",
                    "observation_count": len(rows),
                    "distinct_date_count": len(product_dates),
                    "first_observation_date": product_dates[0],
                    "last_observation_date": product_dates[-1],
                    "model_eligibility_automatically_changed": "false",
                }
            )
        else:
            coverage_rows.append(
                {
                    "canonical_product_id":
                        identity["canonical_product_id"],
                    "tcgplayer_product_id": tcg_id,
                    "product_name": identity["product_name"],
                    "historical_evidence_status":
                        "NO_CERTIFIED_HISTORICAL_PRICE_EVIDENCE",
                    "historical_source": "",
                    "observation_count": 0,
                    "distinct_date_count": 0,
                    "first_observation_date": "",
                    "last_observation_date": "",
                    "model_eligibility_automatically_changed": "false",
                }
            )

            gap_rows.append(
                {
                    "canonical_product_id":
                        identity["canonical_product_id"],
                    "tcgplayer_product_id": tcg_id,
                    "product_name": identity["product_name"],
                    "historical_evidence_status":
                        "NO_CERTIFIED_HISTORICAL_PRICE_EVIDENCE",
                    "gap_reason":
                        "NO_ADMISSIBLE_DIRECT_TCGCSV_MONTHLY_HISTORY",
                    "canonical_universe_membership": "true",
                    "model_exclusion_authorized": "false",
                    "synthetic_price_authorized": "false",
                }
            )

    if len(coverage_rows) != 186:
        fail("coverage ledger must contain exactly 186 rows")

    if len(gap_rows) != 71:
        fail("gap ledger must contain exactly 71 rows")

    output_root.mkdir(parents=True, exist_ok=True)

    history_path = (
        output_root
        / "precollector_historical_price_authority_v2.csv"
    )
    coverage_path = (
        output_root
        / "precollector_historical_price_coverage_v2.csv"
    )
    gaps_path = (
        output_root
        / "precollector_historical_price_gaps_v2.csv"
    )
    summary_path = (
        output_root
        / "precollector_historical_price_authority_v2_summary.json"
    )
    manifest_path = (
        output_root
        / "precollector_historical_price_authority_v2_manifest.json"
    )

    write_csv(history_path, admitted_rows, HISTORY_FIELDS)
    write_csv(coverage_path, coverage_rows, COVERAGE_FIELDS)
    write_csv(gaps_path, gap_rows, GAP_FIELDS)

    date_counts = sorted(
        len(
            {
                str(row["observation_date"])
                for row in product_rows[tcg_id]
            }
        )
        for tcg_id in admitted_products
    )

    summary: dict[str, object] = {
        "status": "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_V2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_product_count": 186,
        "admitted_product_count": len(admitted_products),
        "historical_gap_product_count": len(gap_products),
        "admitted_observation_count": len(admitted_rows),
        "distinct_observation_date_count": len(distinct_dates),
        "first_observation_date": distinct_dates[0],
        "last_observation_date": distinct_dates[-1],
        "minimum_distinct_dates_per_admitted_product": min(date_counts),
        "maximum_distinct_dates_per_admitted_product": max(date_counts),
        "duplicate_product_date_conflict_count": len(conflict_keys),
        "admitted_source": "TCGCSV_ARCHIVE_MONTHLY_DIRECT",
        "source_file": str(archive_path),
        "source_file_sha256": source_sha,
        "ebay_history_admitted": False,
        "universal_combined_ledger_admitted": False,
        "synthetic_case_price_derivation_authorized": False,
        "canonical_product_removal_authorized": False,
        "historical_gap_implies_model_exclusion": False,
        "model_execution_authorized": False,
        "forecast_execution_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_analysis_authorized": False,
        "next_stage":
            "CERTIFY_PRECOLLECTOR_CURRENT_PRICE_AND_AVAILABILITY_EVIDENCE",
    }

    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_files = [
        history_path,
        coverage_path,
        gaps_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_historical_price_authority_v2_manifest",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_universe_identity_sha256": EXPECTED_IDENTITY_SHA,
        "source_file_sha256": source_sha,
        "outputs": [
            {
                "file_name": path.name,
                "byte_length": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in manifest_files
        ],
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage9-package", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    summary = build_authority(
        args.stage9_package.resolve(),
        args.archive.resolve(),
        args.output_root.resolve(),
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())