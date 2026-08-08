from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_CANONICAL_COUNT = 131


def fail(message: str) -> None:
    raise RuntimeError(f"FAIL-CLOSED: {message}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def read_zip_csv(
    package: Path,
    member: str,
) -> tuple[list[dict[str, str]], list[str]]:

    with zipfile.ZipFile(package, "r") as archive:

        if member not in archive.namelist():
            fail(f"missing ZIP member: {member}")

        raw = archive.read(member).decode("utf-8-sig")

    reader = csv.DictReader(raw.splitlines())

    rows = list(reader)
    fields = list(reader.fieldnames or [])

    return rows, fields


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: list[str],
) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--corrected-universe-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--stage14-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--expected-identity-sha",
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    corrected_package = (
        args.corrected_universe_package.resolve()
    )

    stage14_package = (
        args.stage14_package.resolve()
    )

    output_root = (
        args.output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------------
    # Corrected 131 universe
    # ------------------------------------------------------------------------

    canonical_rows, canonical_fields = (
        read_zip_csv(
            corrected_package,
            "precollector_canonical_universe_v2.csv",
        )
    )

    if len(canonical_rows) != EXPECTED_CANONICAL_COUNT:
        fail(
            f"corrected canonical count {len(canonical_rows)} "
            f"!= {EXPECTED_CANONICAL_COUNT}"
        )

    canonical_ids = {
        str(row["canonical_product_id"]).strip()
        for row in canonical_rows
    }

    if len(canonical_ids) != EXPECTED_CANONICAL_COUNT:
        fail(
            "corrected canonical IDs are not unique"
        )

    identity_material = "\n".join(
        f"{row['canonical_product_id']}|{row['product_name']}"
        for row in sorted(
            canonical_rows,
            key=lambda row: int(
                str(row["canonical_product_id"]).split(":")[-1]
            ),
        )
    ) + "\n"

    identity_sha = hashlib.sha256(
        identity_material.encode("utf-8")
    ).hexdigest()

    if identity_sha != args.expected_identity_sha:
        fail(
            "corrected universe identity SHA mismatch"
        )

    # ------------------------------------------------------------------------
    # Prior Stage-14 certified history
    # ------------------------------------------------------------------------

    history_rows, history_fields = (
        read_zip_csv(
            stage14_package,
            "precollector_historical_price_authority_v2.csv",
        )
    )

    if not history_rows:
        fail(
            "Stage-14 historical authority contains no rows"
        )

    coverage_rows_v2, _ = (
        read_zip_csv(
            stage14_package,
            "precollector_historical_price_coverage_v2.csv",
        )
    )

    if len(coverage_rows_v2) != 186:
        fail(
            "Stage-14 coverage ledger is not 186 rows"
        )

    # ------------------------------------------------------------------------
    # Filter to corrected scope
    # ------------------------------------------------------------------------

    rebound_history = [
        row
        for row in history_rows
        if str(
            row.get("canonical_product_id") or ""
        ).strip()
        in canonical_ids
    ]

    # All rebound history must belong to the 131-product authority.
    if any(
        str(row["canonical_product_id"]).strip()
        not in canonical_ids
        for row in rebound_history
    ):
        fail(
            "rebound history contains noncanonical IDs"
        )

    rows_by_product: dict[
        str,
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in rebound_history:
        rows_by_product[
            str(row["canonical_product_id"]).strip()
        ].append(row)

    covered_ids = set(rows_by_product)
    gap_ids = canonical_ids - covered_ids

    # ------------------------------------------------------------------------
    # Duplicate/conflict check
    # ------------------------------------------------------------------------

    prices_by_key: dict[
        tuple[str, str],
        set[str],
    ] = defaultdict(set)

    duplicate_key_count = 0

    seen_keys: set[
        tuple[str, str]
    ] = set()

    for row in rebound_history:

        key = (
            str(row["canonical_product_id"]).strip(),
            str(row["observation_date"]).strip(),
        )

        price = str(
            row["historical_price"]
        ).strip()

        prices_by_key[key].add(price)

        if key in seen_keys:
            duplicate_key_count += 1

        seen_keys.add(key)

    conflict_keys = [
        key
        for key, prices
        in prices_by_key.items()
        if len(prices) > 1
    ]

    if duplicate_key_count != 0:
        fail(
            "rebound history contains duplicate product/date rows"
        )

    if conflict_keys:
        fail(
            f"rebound history contains {len(conflict_keys)} "
            "product/date price conflicts"
        )

    # ------------------------------------------------------------------------
    # Build 131-row coverage ledger
    # ------------------------------------------------------------------------

    canonical_by_id = {
        str(row["canonical_product_id"]).strip(): row
        for row in canonical_rows
    }

    rebound_coverage: list[
        dict[str, object]
    ] = []

    rebound_gaps: list[
        dict[str, object]
    ] = []

    for canonical_id in sorted(
        canonical_ids,
        key=lambda value: int(
            value.split(":")[-1]
        ),
    ):

        identity = canonical_by_id[
            canonical_id
        ]

        product_history = rows_by_product.get(
            canonical_id,
            [],
        )

        dates = sorted(
            {
                str(row["observation_date"]).strip()
                for row in product_history
            }
        )

        if product_history:

            rebound_coverage.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        identity["product_name"],

                    "historical_evidence_status":
                        "CERTIFIED_TCGCSV_MONTHLY_HISTORY",

                    "historical_source":
                        "TCGCSV_ARCHIVE_MONTHLY_DIRECT",

                    "observation_count":
                        len(product_history),

                    "distinct_date_count":
                        len(dates),

                    "first_observation_date":
                        dates[0],

                    "last_observation_date":
                        dates[-1],

                    "model_eligibility_automatically_changed":
                        "false",
                }
            )

        else:

            rebound_coverage.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        identity["product_name"],

                    "historical_evidence_status":
                        "NO_CERTIFIED_HISTORICAL_PRICE_EVIDENCE",

                    "historical_source":
                        "",

                    "observation_count":
                        0,

                    "distinct_date_count":
                        0,

                    "first_observation_date":
                        "",

                    "last_observation_date":
                        "",

                    "model_eligibility_automatically_changed":
                        "false",
                }
            )

            rebound_gaps.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        identity["product_name"],

                    "historical_evidence_status":
                        "NO_CERTIFIED_HISTORICAL_PRICE_EVIDENCE",

                    "gap_reason":
                        "NO_ADMISSIBLE_DIRECT_TCGCSV_MONTHLY_HISTORY",

                    "canonical_universe_membership":
                        "true",

                    "model_exclusion_authorized":
                        "false",

                    "synthetic_price_authorized":
                        "false",
                }
            )

    if len(rebound_coverage) != 131:
        fail(
            "rebound coverage ledger is not 131 rows"
        )

    # ------------------------------------------------------------------------
    # Distinct-date diagnostics
    # ------------------------------------------------------------------------

    all_dates = sorted(
        {
            str(row["observation_date"]).strip()
            for row in rebound_history
        }
    )

    date_counts = sorted(
        len(
            {
                str(row["observation_date"]).strip()
                for row in rows_by_product[canonical_id]
            }
        )
        for canonical_id in covered_ids
    )

    # ------------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------------

    history_path = (
        output_root
        / "precollector_historical_price_authority_v3.csv"
    )

    coverage_path = (
        output_root
        / "precollector_historical_price_coverage_v3.csv"
    )

    gaps_path = (
        output_root
        / "precollector_historical_price_gaps_v3.csv"
    )

    summary_path = (
        output_root
        / "precollector_historical_price_authority_v3_summary.json"
    )

    manifest_path = (
        output_root
        / "precollector_historical_price_authority_v3_manifest.json"
    )

    write_csv(
        history_path,
        rebound_history,
        history_fields,
    )

    coverage_fields = [
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

    write_csv(
        coverage_path,
        rebound_coverage,
        coverage_fields,
    )

    gap_fields = [
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "historical_evidence_status",
        "gap_reason",
        "canonical_universe_membership",
        "model_exclusion_authorized",
        "synthetic_price_authorized",
    ]

    write_csv(
        gaps_path,
        rebound_gaps,
        gap_fields,
    )

    removed_history_rows = (
        len(history_rows)
        - len(rebound_history)
    )

    removed_covered_products = (
        len(
            {
                str(row["canonical_product_id"]).strip()
                for row in history_rows
            }
        )
        - len(covered_ids)
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_V3",

        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),

        "canonical_product_count":
            131,

        "corrected_identity_sha256":
            identity_sha,

        "covered_product_count":
            len(covered_ids),

        "historical_gap_product_count":
            len(gap_ids),

        "historical_observation_count":
            len(rebound_history),

        "distinct_observation_date_count":
            len(all_dates),

        "first_observation_date":
            all_dates[0]
            if all_dates
            else "",

        "last_observation_date":
            all_dates[-1]
            if all_dates
            else "",

        "minimum_distinct_dates_per_covered_product":
            min(date_counts)
            if date_counts
            else 0,

        "maximum_distinct_dates_per_covered_product":
            max(date_counts)
            if date_counts
            else 0,

        "duplicate_product_date_rows":
            duplicate_key_count,

        "conflicting_product_date_prices":
            len(conflict_keys),

        "prior_stage14_observation_count":
            len(history_rows),

        "case_scope_rows_removed":
            removed_history_rows,

        "case_scope_covered_products_removed":
            removed_covered_products,

        "historical_recollection_performed":
            False,

        "case_price_normalization_performed":
            False,

        "historical_gap_implies_model_exclusion":
            False,

        "model_execution_authorized":
            False,

        "authorized_next_stage":
            "FRESH_131_PRODUCT_CURRENT_PRICE_AND_HIGH_RECALL_EBAY_COLLECTION",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
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
            "precollector_historical_price_authority_v3",

        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),

        "corrected_identity_sha256":
            identity_sha,

        "corrected_universe_package_sha256":
            sha256_file(
                corrected_package
            ),

        "stage14_source_package_sha256":
            sha256_file(
                stage14_package
            ),

        "members": [
            {
                "file_name":
                    path.name,

                "byte_length":
                    path.stat().st_size,

                "sha256":
                    sha256_file(path),
            }
            for path in manifest_files
        ],
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "PASS_PRECOLLECTOR_HISTORICAL_PRICE_AUTHORITY_V3"
    )

    print(
        "CANONICAL_PRODUCT_COUNT=131"
    )

    print(
        f"COVERED_HISTORY_PRODUCTS={len(covered_ids)}"
    )

    print(
        f"HISTORICAL_GAP_PRODUCTS={len(gap_ids)}"
    )

    print(
        f"HISTORICAL_OBSERVATION_ROWS={len(rebound_history)}"
    )

    print(
        f"CASE_SCOPE_HISTORY_ROWS_REMOVED={removed_history_rows}"
    )

    print(
        "HISTORICAL_RECOLLECTION_PERFORMED=FALSE"
    )

    print(
        "CASE_PRICE_NORMALIZATION_PERFORMED=FALSE"
    )

    print(
        "MODEL_EXECUTION_AUTHORIZED=FALSE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())