from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile

from datetime import datetime, timezone
from pathlib import Path


EXPECTED_CANONICAL_COUNT = 131
EXPECTED_PRICE_PRODUCTS = 121
EXPECTED_GAP_PRODUCTS = 10


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        return list(
            csv.DictReader(handle)
        )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: list[str],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def load_universe(
    package: Path,
) -> list[dict[str, str]]:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        member = (
            "precollector_canonical_universe_v2.csv"
        )

        if member not in archive.namelist():
            fail(
                f"missing corrected universe member: {member}"
            )

        raw = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    rows = list(
        csv.DictReader(
            raw.splitlines()
        )
    )

    if len(rows) != EXPECTED_CANONICAL_COUNT:
        fail(
            f"corrected universe count {len(rows)} "
            f"!= {EXPECTED_CANONICAL_COUNT}"
        )

    return rows


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--universe-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--fresh-prices",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--fresh-coverage",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--fresh-group-audit",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--fresh-summary",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--fresh-manifest",
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

    universe = load_universe(
        args.universe_package
    )

    canonical_by_id = {
        clean(
            row[
                "canonical_product_id"
            ]
        ): row
        for row in universe
    }

    if len(canonical_by_id) != 131:
        fail(
            "canonical IDs are not uniquely 131"
        )

    identity_material = "\n".join(
        f"{row['canonical_product_id']}|{row['product_name']}"
        for row in sorted(
            universe,
            key=lambda row: int(
                clean(
                    row[
                        "canonical_product_id"
                    ]
                ).split(":")[-1]
            ),
        )
    ) + "\n"

    identity_sha = hashlib.sha256(
        identity_material.encode(
            "utf-8"
        )
    ).hexdigest()

    if identity_sha != args.expected_identity_sha:
        fail(
            "corrected identity SHA mismatch"
        )

    prices = read_csv(
        args.fresh_prices
    )

    coverage = read_csv(
        args.fresh_coverage
    )

    group_audit = read_csv(
        args.fresh_group_audit
    )

    fresh_summary = json.loads(
        args.fresh_summary.read_text(
            encoding="utf-8-sig"
        )
    )

    if len(coverage) != 131:
        fail(
            "fresh coverage ledger is not 131 rows"
        )

    failed_groups = [
        row
        for row in group_audit
        if clean(
            row.get(
                "request_status"
            )
        ).upper()
        != "PASS"
    ]

    if failed_groups:
        fail(
            f"fresh source has {len(failed_groups)} failed group requests"
        )

    # ------------------------------------------------------------------------
    # Validate direct price observations
    # ------------------------------------------------------------------------

    price_by_id = {}

    for row in prices:

        canonical_id = clean(
            row.get(
                "canonical_product_id"
            )
        )

        if canonical_id not in canonical_by_id:
            fail(
                "price row references noncanonical product: "
                + canonical_id
            )

        if canonical_id in price_by_id:
            fail(
                "duplicate current-price product row: "
                + canonical_id
            )

        tcg_id = clean(
            row.get(
                "tcgplayer_product_id"
            )
        )

        expected_tcg = (
            canonical_id.split(":")[-1]
        )

        if tcg_id != expected_tcg:
            fail(
                "TCGplayer identity mismatch for "
                + canonical_id
            )

        try:
            selected_price = float(
                clean(
                    row.get(
                        "selected_price"
                    )
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            fail(
                "invalid selected price for "
                + canonical_id
            )

        if selected_price <= 0:
            fail(
                "non-positive selected price for "
                + canonical_id
            )

        if clean(
            row.get(
                "source_name"
            )
        ) != "TCGCSV_LIVE":
            fail(
                "unexpected current-price source for "
                + canonical_id
            )

        price_by_id[
            canonical_id
        ] = row

    if len(price_by_id) != EXPECTED_PRICE_PRODUCTS:
        fail(
            f"current-price product count {len(price_by_id)} "
            f"!= {EXPECTED_PRICE_PRODUCTS}"
        )

    # ------------------------------------------------------------------------
    # Build governed 131-row coverage ledger
    # ------------------------------------------------------------------------

    authority_rows = []
    coverage_rows = []
    gap_rows = []

    for canonical_id in sorted(
        canonical_by_id,
        key=lambda value: int(
            value.split(":")[-1]
        ),
    ):

        identity = canonical_by_id[
            canonical_id
        ]

        price_row = price_by_id.get(
            canonical_id
        )

        if price_row is not None:

            authority_rows.append(
                dict(price_row)
            )

            coverage_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        clean(
                            identity[
                                "product_name"
                            ]
                        ),

                    "current_price_evidence_status":
                        "CERTIFIED_TCGCSV_LIVE_CURRENT_PRICE",

                    "selected_price":
                        clean(
                            price_row[
                                "selected_price"
                            ]
                        ),

                    "source_name":
                        "TCGCSV_LIVE",

                    "observation_date":
                        clean(
                            price_row[
                                "observation_date"
                            ]
                        ),

                    "model_eligibility_automatically_changed":
                        "false",
                }
            )

        else:

            coverage_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        clean(
                            identity[
                                "product_name"
                            ]
                        ),

                    "current_price_evidence_status":
                        "NO_CERTIFIED_CURRENT_PRICE_EVIDENCE",

                    "selected_price":
                        "",

                    "source_name":
                        "",

                    "observation_date":
                        "",

                    "model_eligibility_automatically_changed":
                        "false",
                }
            )

            gap_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        clean(
                            identity[
                                "product_name"
                            ]
                        ),

                    "gap_reason":
                        "NO_POSITIVE_TCGCSV_LIVE_PRICE_RECORD",

                    "canonical_universe_membership":
                        "true",

                    "model_exclusion_authorized":
                        "false",

                    "prediction_exclusion_authorized":
                        "false",

                    "synthetic_price_authorized":
                        "false",
                }
            )

    if len(authority_rows) != 121:
        fail(
            "authority rows are not 121"
        )

    if len(coverage_rows) != 131:
        fail(
            "coverage rows are not 131"
        )

    if len(gap_rows) != 10:
        fail(
            "gap rows are not 10"
        )

    observation_dates = sorted(
        {
            clean(
                row[
                    "observation_date"
                ]
            )
            for row in authority_rows
            if clean(
                row.get(
                    "observation_date"
                )
            )
        }
    )

    if len(observation_dates) != 1:
        fail(
            "fresh current-price observations do not share one operating date"
        )

    # ------------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------------

    output_root = (
        args.output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    authority_path = (
        output_root
        / "precollector_current_price_authority_v2.csv"
    )

    coverage_path = (
        output_root
        / "precollector_current_price_coverage_v2.csv"
    )

    gaps_path = (
        output_root
        / "precollector_current_price_gaps_v2.csv"
    )

    summary_path = (
        output_root
        / "precollector_current_price_authority_v2_summary.json"
    )

    manifest_path = (
        output_root
        / "precollector_current_price_authority_v2_manifest.json"
    )

    authority_fields = list(
        authority_rows[0].keys()
    )

    write_csv(
        authority_path,
        authority_rows,
        authority_fields,
    )

    write_csv(
        coverage_path,
        coverage_rows,
        [
            "canonical_product_id",
            "tcgplayer_product_id",
            "product_name",
            "current_price_evidence_status",
            "selected_price",
            "source_name",
            "observation_date",
            "model_eligibility_automatically_changed",
        ],
    )

    write_csv(
        gaps_path,
        gap_rows,
        [
            "canonical_product_id",
            "tcgplayer_product_id",
            "product_name",
            "gap_reason",
            "canonical_universe_membership",
            "model_exclusion_authorized",
            "prediction_exclusion_authorized",
            "synthetic_price_authorized",
        ],
    )

    source_manifest_sha = sha256_file(
        args.fresh_manifest
    )

    source_summary_sha = sha256_file(
        args.fresh_summary
    )

    source_prices_sha = sha256_file(
        args.fresh_prices
    )

    source_coverage_sha = sha256_file(
        args.fresh_coverage
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_V2",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_product_count":
            131,

        "corrected_identity_sha256":
            identity_sha,

        "certified_current_price_products":
            121,

        "current_price_gap_products":
            10,

        "current_price_observation_rows":
            len(authority_rows),

        "observation_date":
            observation_dates[0],

        "tcgcsv_group_request_failures":
            0,

        "source_name":
            "TCGCSV_LIVE",

        "source_stage":
            "STAGE_15H",

        "fresh_source_prices_sha256":
            source_prices_sha,

        "fresh_source_coverage_sha256":
            source_coverage_sha,

        "fresh_source_summary_sha256":
            source_summary_sha,

        "fresh_source_manifest_sha256":
            source_manifest_sha,

        "ebay_used_as_current_price_source":
            False,

        "synthetic_price_used":
            False,

        "case_price_conversion_used":
            False,

        "missing_current_price_implies_model_exclusion":
            False,

        "model_execution_authorized":
            False,

        "authorized_next_stage":
            "RESOLVE_AND_CERTIFY_PRECOLLECTOR_AVAILABILITY_EVIDENCE",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    package_members = [
        authority_path,
        coverage_path,
        gaps_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_current_price_authority_v2",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "corrected_identity_sha256":
            identity_sha,

        "source_stage":
            "STAGE_15H",

        "members": [
            {
                "file_name":
                    path.name,

                "byte_length":
                    path.stat().st_size,

                "sha256":
                    sha256_file(path),
            }
            for path in package_members
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
        "PASS_PRECOLLECTOR_CURRENT_PRICE_AUTHORITY_V2"
    )

    print(
        "CANONICAL_PRODUCT_COUNT=131"
    )

    print(
        "CERTIFIED_CURRENT_PRICE_PRODUCTS=121"
    )

    print(
        "CURRENT_PRICE_GAP_PRODUCTS=10"
    )

    print(
        f"OBSERVATION_DATE={observation_dates[0]}"
    )

    print(
        "TCGCSV_GROUP_FAILURES=0"
    )

    print(
        "EBAY_USED_AS_CURRENT_PRICE_SOURCE=FALSE"
    )

    print(
        "SYNTHETIC_PRICE_USED=FALSE"
    )

    print(
        "MISSING_CURRENT_PRICE_IMPLIES_MODEL_EXCLUSION=FALSE"
    )

    print(
        "MODEL_EXECUTION_AUTHORIZED=FALSE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())