from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


EXPECTED_CANONICAL = 131
EXPECTED_HISTORY_PRODUCTS = 115
EXPECTED_HISTORY_ROWS = 3390
HORIZONS = (90, 180, 365, 1095, 1825)


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
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def read_zip_csv(
    package: Path,
    member: str,
) -> list[dict[str, str]]:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        if member not in archive.namelist():
            fail(
                f"missing ZIP member {member}"
            )

        raw = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    return list(
        csv.DictReader(
            raw.splitlines()
        )
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


def parse_date(value: object) -> date:
    return date.fromisoformat(
        clean(value)[:10]
    )


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--canonical-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--history-package",
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

    canonical_rows = read_zip_csv(
        args.canonical_package,
        "precollector_canonical_universe_v2.csv",
    )

    history_rows = read_zip_csv(
        args.history_package,
        "precollector_historical_price_authority_v3.csv",
    )

    if len(canonical_rows) != EXPECTED_CANONICAL:
        fail(
            f"canonical row count {len(canonical_rows)} "
            f"!= {EXPECTED_CANONICAL}"
        )

    if len(history_rows) != EXPECTED_HISTORY_ROWS:
        fail(
            f"historical row count {len(history_rows)} "
            f"!= {EXPECTED_HISTORY_ROWS}"
        )

    canonical_ids = {
        clean(
            row["canonical_product_id"]
        )
        for row in canonical_rows
    }

    if len(canonical_ids) != EXPECTED_CANONICAL:
        fail(
            "canonical product IDs are not unique"
        )

    identity_material = "\n".join(
        f"{row['canonical_product_id']}|{row['product_name']}"
        for row in sorted(
            canonical_rows,
            key=lambda row: int(
                clean(
                    row["canonical_product_id"]
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
            "canonical identity SHA mismatch"
        )

    canonical_by_id = {
        clean(
            row["canonical_product_id"]
        ): row
        for row in canonical_rows
    }

    history_by_product: dict[
        str,
        list[tuple[date, float]]
    ] = defaultdict(list)

    seen_keys = set()

    for row in history_rows:

        canonical_id = clean(
            row["canonical_product_id"]
        )

        if canonical_id not in canonical_ids:
            fail(
                "history contains noncanonical product"
            )

        observation_date = parse_date(
            row["observation_date"]
        )

        try:
            price = float(
                clean(
                    row["historical_price"]
                )
            )
        except ValueError as exc:
            raise RuntimeError(
                "FAIL-CLOSED: nonnumeric historical price"
            ) from exc

        if price <= 0:
            fail(
                "nonpositive historical price"
            )

        key = (
            canonical_id,
            observation_date,
        )

        if key in seen_keys:
            fail(
                "duplicate canonical product/date history row"
            )

        seen_keys.add(key)

        history_by_product[
            canonical_id
        ].append(
            (
                observation_date,
                price,
            )
        )

    if len(history_by_product) != EXPECTED_HISTORY_PRODUCTS:
        fail(
            f"historical product count "
            f"{len(history_by_product)} "
            f"!= {EXPECTED_HISTORY_PRODUCTS}"
        )

    for canonical_id in history_by_product:
        history_by_product[
            canonical_id
        ].sort(
            key=lambda item: item[0]
        )

    # ========================================================================
    # Global history diagnostics
    # ========================================================================

    global_dates = sorted(
        {
            obs_date
            for observations
            in history_by_product.values()
            for obs_date, _
            in observations
        }
    )

    if not global_dates:
        fail(
            "history contains no dates"
        )

    global_first = global_dates[0]
    global_last = global_dates[-1]
    global_span_days = (
        global_last - global_first
    ).days

    # ========================================================================
    # Temporal fold ledger
    # ========================================================================

    fold_rows = []

    product_horizon_counts = defaultdict(
        int
    )

    horizon_counts = defaultdict(
        int
    )

    horizon_product_sets = defaultdict(
        set
    )

    fold_number = 0

    for canonical_id in sorted(
        canonical_ids,
        key=lambda value: int(
            value.split(":")[-1]
        ),
    ):

        observations = history_by_product.get(
            canonical_id,
            [],
        )

        if not observations:
            continue

        observation_dates = [
            item[0]
            for item in observations
        ]

        for horizon in HORIZONS:

            for origin_index, (
                origin_date,
                origin_price,
            ) in enumerate(
                observations
            ):

                target_date = (
                    origin_date
                    + timedelta(
                        days=horizon
                    )
                )

                endpoint = None

                for endpoint_index in range(
                    origin_index + 1,
                    len(observations),
                ):

                    candidate_date, candidate_price = (
                        observations[
                            endpoint_index
                        ]
                    )

                    if candidate_date >= target_date:
                        endpoint = (
                            endpoint_index,
                            candidate_date,
                            candidate_price,
                        )
                        break

                if endpoint is None:
                    continue

                (
                    endpoint_index,
                    endpoint_date,
                    endpoint_price,
                ) = endpoint

                training_observation_count = (
                    origin_index + 1
                )

                if training_observation_count <= 0:
                    fail(
                        "invalid training observation count"
                    )

                if endpoint_date <= origin_date:
                    fail(
                        "validation endpoint is not after origin"
                    )

                actual_elapsed_days = (
                    endpoint_date
                    - origin_date
                ).days

                endpoint_drift_days = (
                    endpoint_date
                    - target_date
                ).days

                if actual_elapsed_days < horizon:
                    fail(
                        "endpoint violates on-or-after target rule"
                    )

                if endpoint_drift_days < 0:
                    fail(
                        "negative endpoint drift"
                    )

                fold_number += 1

                fold_id = (
                    f"PCF-{fold_number:06d}"
                )

                fold_rows.append(
                    {
                        "fold_id":
                            fold_id,

                        "canonical_product_id":
                            canonical_id,

                        "tcgplayer_product_id":
                            canonical_id.split(":")[-1],

                        "product_name":
                            clean(
                                canonical_by_id[
                                    canonical_id
                                ][
                                    "product_name"
                                ]
                            ),

                        "requested_horizon_days":
                            horizon,

                        "origin_date":
                            origin_date.isoformat(),

                        "origin_price":
                            origin_price,

                        "target_date":
                            target_date.isoformat(),

                        "realized_endpoint_date":
                            endpoint_date.isoformat(),

                        "realized_endpoint_price":
                            endpoint_price,

                        "actual_elapsed_days":
                            actual_elapsed_days,

                        "endpoint_drift_days":
                            endpoint_drift_days,

                        "training_first_date":
                            observations[
                                0
                            ][
                                0
                            ].isoformat(),

                        "training_last_date":
                            origin_date.isoformat(),

                        "training_observation_count":
                            training_observation_count,

                        "future_data_in_training":
                            "false",

                        "endpoint_rule":
                            "FIRST_OBSERVATION_ON_OR_AFTER_TARGET",
                    }
                )

                product_horizon_counts[
                    (
                        canonical_id,
                        horizon,
                    )
                ] += 1

                horizon_counts[
                    horizon
                ] += 1

                horizon_product_sets[
                    horizon
                ].add(
                    canonical_id
                )

    # ========================================================================
    # 131 x 5 horizon applicability ledger
    # ========================================================================

    applicability_rows = []

    for canonical_id in sorted(
        canonical_ids,
        key=lambda value: int(
            value.split(":")[-1]
        ),
    ):

        product_name = clean(
            canonical_by_id[
                canonical_id
            ][
                "product_name"
            ]
        )

        observation_count = len(
            history_by_product.get(
                canonical_id,
                [],
            )
        )

        for horizon in HORIZONS:

            realized_fold_count = (
                product_horizon_counts[
                    (
                        canonical_id,
                        horizon,
                    )
                ]
            )

            if realized_fold_count > 0:

                support_status = (
                    "DIRECT_HISTORICAL_VALIDATION_SUPPORTED"
                )

            else:

                support_status = (
                    "NO_DIRECT_HISTORICAL_VALIDATION_SUPPORT"
                )

            applicability_rows.append(
                {
                    "canonical_product_id":
                        canonical_id,

                    "tcgplayer_product_id":
                        canonical_id.split(":")[-1],

                    "product_name":
                        product_name,

                    "requested_horizon_days":
                        horizon,

                    "certified_history_observation_count":
                        observation_count,

                    "realized_fold_count":
                        realized_fold_count,

                    "direct_historical_validation_status":
                        support_status,

                    "canonical_membership":
                        "true",

                    "model_exclusion_authorized":
                        "false",

                    "prediction_exclusion_authorized":
                        "false",
                }
            )

    expected_applicability_rows = (
        EXPECTED_CANONICAL
        * len(HORIZONS)
    )

    if (
        len(applicability_rows)
        != expected_applicability_rows
    ):
        fail(
            "horizon applicability ledger row count mismatch"
        )

    # ========================================================================
    # Horizon summary
    # ========================================================================

    horizon_summary_rows = []

    for horizon in HORIZONS:

        supported_products = len(
            horizon_product_sets[
                horizon
            ]
        )

        unsupported_products = (
            EXPECTED_CANONICAL
            - supported_products
        )

        realized_folds = (
            horizon_counts[
                horizon
            ]
        )

        horizon_summary_rows.append(
            {
                "requested_horizon_days":
                    horizon,

                "products_with_direct_validation_support":
                    supported_products,

                "products_without_direct_validation_support":
                    unsupported_products,

                "realized_fold_count":
                    realized_folds,

                "canonical_product_count":
                    EXPECTED_CANONICAL,

                "unsupported_products_excluded":
                    "false",
            }
        )

    # ========================================================================
    # Fold integrity validation
    # ========================================================================

    for row in fold_rows:

        if (
            row[
                "future_data_in_training"
            ]
            != "false"
        ):
            fail(
                "future-data leakage flag found"
            )

        if (
            parse_date(
                row[
                    "training_last_date"
                ]
            )
            != parse_date(
                row[
                    "origin_date"
                ]
            )
        ):
            fail(
                "training last date does not equal fold origin"
            )

        if (
            parse_date(
                row[
                    "realized_endpoint_date"
                ]
            )
            <
            parse_date(
                row[
                    "target_date"
                ]
            )
        ):
            fail(
                "realized endpoint occurs before target date"
            )

    # ========================================================================
    # Outputs
    # ========================================================================

    output_root = (
        args.output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    folds_path = (
        output_root
        / "precollector_temporal_fold_ledger_v1.csv"
    )

    applicability_path = (
        output_root
        / "precollector_horizon_applicability_ledger_v1.csv"
    )

    horizon_summary_path = (
        output_root
        / "precollector_horizon_support_summary_v1.csv"
    )

    summary_path = (
        output_root
        / "precollector_temporal_fold_and_horizon_applicability_v1_summary.json"
    )

    manifest_path = (
        output_root
        / "precollector_temporal_fold_and_horizon_applicability_v1_manifest.json"
    )

    fold_fields = [
        "fold_id",
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "requested_horizon_days",
        "origin_date",
        "origin_price",
        "target_date",
        "realized_endpoint_date",
        "realized_endpoint_price",
        "actual_elapsed_days",
        "endpoint_drift_days",
        "training_first_date",
        "training_last_date",
        "training_observation_count",
        "future_data_in_training",
        "endpoint_rule",
    ]

    write_csv(
        folds_path,
        fold_rows,
        fold_fields,
    )

    applicability_fields = [
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "requested_horizon_days",
        "certified_history_observation_count",
        "realized_fold_count",
        "direct_historical_validation_status",
        "canonical_membership",
        "model_exclusion_authorized",
        "prediction_exclusion_authorized",
    ]

    write_csv(
        applicability_path,
        applicability_rows,
        applicability_fields,
    )

    horizon_summary_fields = [
        "requested_horizon_days",
        "products_with_direct_validation_support",
        "products_without_direct_validation_support",
        "realized_fold_count",
        "canonical_product_count",
        "unsupported_products_excluded",
    ]

    write_csv(
        horizon_summary_path,
        horizon_summary_rows,
        horizon_summary_fields,
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_TEMPORAL_FOLD_AND_HORIZON_APPLICABILITY_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_product_count":
            EXPECTED_CANONICAL,

        "canonical_identity_sha256":
            identity_sha,

        "historical_product_count":
            len(
                history_by_product
            ),

        "historical_observation_rows":
            len(
                history_rows
            ),

        "global_first_history_date":
            global_first.isoformat(),

        "global_last_history_date":
            global_last.isoformat(),

        "global_history_span_days":
            global_span_days,

        "total_realized_fold_rows":
            len(
                fold_rows
            ),

        "horizon_support": {
            str(horizon): {
                "supported_products":
                    len(
                        horizon_product_sets[
                            horizon
                        ]
                    ),

                "unsupported_products":
                    EXPECTED_CANONICAL
                    - len(
                        horizon_product_sets[
                            horizon
                        ]
                    ),

                "realized_fold_count":
                    horizon_counts[
                        horizon
                    ],
            }
            for horizon in HORIZONS
        },

        "endpoint_tolerance_imposed":
            False,

        "future_data_leakage_detected":
            False,

        "model_fitting_performed":
            False,

        "model_treatments_assigned":
            0,

        "model_exclusions_assigned":
            0,

        "production_forecast_authorized":
            False,

        "authorized_next_stage":
            "IMPLEMENT_PRECOLLECTOR_DIAGNOSTIC_TOURNAMENT_ENGINE",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_members = [
        folds_path,
        applicability_path,
        horizon_summary_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_temporal_fold_and_horizon_applicability_v1",

        "canonical_identity_sha256":
            identity_sha,

        "canonical_package_sha256":
            sha256_file(
                args.canonical_package
            ),

        "history_package_sha256":
            sha256_file(
                args.history_package
            ),

        "members": [
            {
                "file_name":
                    path.name,

                "byte_length":
                    path.stat().st_size,

                "sha256":
                    sha256_file(
                        path
                    ),
            }
            for path in manifest_members
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
        "PASS_PRECOLLECTOR_TEMPORAL_FOLD_AND_HORIZON_APPLICABILITY_V1"
    )

    print(
        "CANONICAL_PRODUCT_COUNT=131"
    )

    print(
        f"HISTORICAL_PRODUCT_COUNT={len(history_by_product)}"
    )

    print(
        f"HISTORICAL_OBSERVATION_ROWS={len(history_rows)}"
    )

    print(
        f"GLOBAL_FIRST_HISTORY_DATE={global_first.isoformat()}"
    )

    print(
        f"GLOBAL_LAST_HISTORY_DATE={global_last.isoformat()}"
    )

    print(
        f"GLOBAL_HISTORY_SPAN_DAYS={global_span_days}"
    )

    print(
        f"TOTAL_REALIZED_FOLD_ROWS={len(fold_rows)}"
    )

    for horizon in HORIZONS:

        print(
            f"HORIZON_{horizon}_SUPPORTED_PRODUCTS="
            f"{len(horizon_product_sets[horizon])}"
        )

        print(
            f"HORIZON_{horizon}_REALIZED_FOLDS="
            f"{horizon_counts[horizon]}"
        )

    print(
        "ENDPOINT_TOLERANCE_IMPOSED=FALSE"
    )

    print(
        "FUTURE_DATA_LEAKAGE_DETECTED=FALSE"
    )

    print(
        "MODEL_FITTING_PERFORMED=FALSE"
    )

    print(
        "MODEL_EXCLUSIONS_ASSIGNED=0"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())