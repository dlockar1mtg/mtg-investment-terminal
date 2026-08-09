from __future__ import annotations

import argparse
import csv
import json
import zipfile

from datetime import datetime, timezone
from pathlib import Path


MODELS = (
    "LAST_VALUE",
    "DRIFT",
    "LOG_DRIFT",
    "ROBUST_TREND",
    "EXPONENTIAL_SMOOTHING",
    "RIDGE_REGRESSION",
    "HUBER_REGRESSION",
    "RANDOM_FOREST",
    "GRADIENT_BOOSTING",
    "PEER_MEDIAN_RETURN",
    "PEER_WEIGHTED_RETURN",
    "ROUTE_ENSEMBLE",
    "GLOBAL_ENSEMBLE",
)

FEATURES = (
    "PRICE_ONLY",
    "PRICE_PLUS_AGE",
    "PRICE_PLUS_PATH_STABILITY",
    "PRICE_PLUS_LIQUIDITY",
    "PRICE_PLUS_SOURCE_DISAGREEMENT",
    "DATA_QUALITY_WEIGHTED",
    "ROBUST_FULL_EVIDENCE",
)

DIRECT_FEATURES = {
    "PRICE_ONLY",
    "PRICE_PLUS_AGE",
    "PRICE_PLUS_PATH_STABILITY",
}

TARGETS = (
    "RAW_PRICE_CHANGE",
    "LOG_PRICE_CHANGE",
    "RETURN",
    "ANNUALIZED_RETURN_WHERE_DEFINED",
)

HORIZONS = (
    90,
    180,
    365,
    1095,
    1825,
)

DIRECT_HORIZONS = {
    90,
    180,
    365,
}


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: list[str],
) -> None:

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)


def load_stage15t(
    package: Path,
) -> dict:

    member = (
        "precollector_temporal_fold_and_horizon_applicability_v1_summary.json"
    )

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        if member not in archive.namelist():
            fail(
                "Stage 15T summary missing"
            )

        return json.loads(
            archive.read(
                member
            ).decode(
                "utf-8-sig"
            )
        )


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--stage15t-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    stage15t = load_stage15t(
        args.stage15t_package
    )

    expected_support = {
        90: (115, 3052),
        180: (115, 2715),
        365: (115, 2036),
        1095: (0, 0),
        1825: (0, 0),
    }

    for horizon, expected in expected_support.items():

        actual = (
            stage15t[
                "horizon_support"
            ][
                str(horizon)
            ]
        )

        if (
            int(
                actual[
                    "supported_products"
                ]
            )
            != expected[0]
        ):
            fail(
                f"horizon {horizon} product support drift"
            )

        if (
            int(
                actual[
                    "realized_fold_count"
                ]
            )
            != expected[1]
        ):
            fail(
                f"horizon {horizon} fold count drift"
            )

    rows = []

    direct = 0
    feature_blocked = 0
    long_blocked = 0

    sequence = 0

    for model in MODELS:
        for feature in FEATURES:
            for target in TARGETS:
                for horizon in HORIZONS:

                    sequence += 1

                    if horizon not in DIRECT_HORIZONS:

                        status = (
                            "BLOCKED_NO_REALIZED_LONG_HORIZON_FOLDS"
                        )

                        reason = (
                            "No realized direct-validation folds."
                        )

                        authorized = False
                        long_blocked += 1

                    elif feature not in DIRECT_FEATURES:

                        status = (
                            "BLOCKED_POINT_IN_TIME_FEATURE_EVIDENCE"
                        )

                        reason = (
                            "Feature was not certified as available "
                            "at historical fold origin."
                        )

                        authorized = False
                        feature_blocked += 1

                    else:

                        status = (
                            "DIRECT_OOS_EXECUTABLE"
                        )

                        reason = (
                            "Direct horizon support and point-in-time-safe "
                            "features are both present."
                        )

                        authorized = True
                        direct += 1

                    rows.append(
                        {
                            "combination_id":
                                f"PCM-{sequence:04d}",

                            "model_family":
                                model,

                            "feature_variant":
                                feature,

                            "target_transformation":
                                target,

                            "requested_horizon_days":
                                horizon,

                            "execution_status":
                                status,

                            "execution_reason":
                                reason,

                            "direct_oos_authorized":
                                str(
                                    authorized
                                ).lower(),

                            "production_model_authorized":
                                "false",

                            "forecast_authorized":
                                "false",

                            "monte_carlo_authorized":
                                "false",

                            "ranking_authorized":
                                "false",
                        }
                    )

    if len(rows) != 1820:
        fail(
            "matrix is not 1820 combinations"
        )

    if direct != 468:
        fail(
            "direct OOS count is not 468"
        )

    if feature_blocked != 624:
        fail(
            "feature-blocked count is not 624"
        )

    if long_blocked != 728:
        fail(
            "long-horizon-blocked count is not 728"
        )

    root = args.output_root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    matrix_path = (
        root
        / "precollector_executable_tournament_matrix_v1.csv"
    )

    summary_path = (
        root
        / "precollector_executable_tournament_matrix_v1_summary.json"
    )

    manifest_path = (
        root
        / "precollector_executable_tournament_matrix_v1_manifest.json"
    )

    fields = [
        "combination_id",
        "model_family",
        "feature_variant",
        "target_transformation",
        "requested_horizon_days",
        "execution_status",
        "execution_reason",
        "direct_oos_authorized",
        "production_model_authorized",
        "forecast_authorized",
        "monte_carlo_authorized",
        "ranking_authorized",
    ]

    write_csv(
        matrix_path,
        rows,
        fields,
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_EXECUTABLE_TOURNAMENT_MATRIX_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "theoretical_combination_count":
            len(rows),

        "direct_oos_executable_combinations":
            direct,

        "blocked_point_in_time_feature_combinations":
            feature_blocked,

        "blocked_long_horizon_combinations":
            long_blocked,

        "direct_oos_horizons": [
            90,
            180,
            365,
        ],

        "direct_oos_feature_variants": [
            "PRICE_ONLY",
            "PRICE_PLUS_AGE",
            "PRICE_PLUS_PATH_STABILITY",
        ],

        "future_information_leakage_authorized":
            False,

        "model_fitting_performed":
            False,

        "monte_carlo_execution_authorized":
            False,

        "production_model_selection_authorized":
            False,

        "forecast_execution_authorized":
            False,

        "ranking_execution_authorized":
            False,

        "authorized_next_stage":
            "IMPLEMENT_AND_RUN_PRECOLLECTOR_DIRECT_OOS_TOURNAMENT",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "manifest_id":
            "precollector_executable_tournament_matrix_v1",

        "matrix_file":
            matrix_path.name,

        "summary_file":
            summary_path.name,
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
        "PASS_PRECOLLECTOR_EXECUTABLE_TOURNAMENT_MATRIX_V1"
    )

    print(
        f"THEORETICAL_COMBINATIONS={len(rows)}"
    )

    print(
        f"DIRECT_OOS_EXECUTABLE_COMBINATIONS={direct}"
    )

    print(
        f"BLOCKED_POINT_IN_TIME_FEATURE_COMBINATIONS={feature_blocked}"
    )

    print(
        f"BLOCKED_LONG_HORIZON_COMBINATIONS={long_blocked}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())