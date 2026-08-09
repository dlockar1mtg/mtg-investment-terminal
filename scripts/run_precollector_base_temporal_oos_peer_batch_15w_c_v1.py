from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import zipfile

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from scipy.stats import spearmanr


MODELS = (
    "PEER_MEDIAN_RETURN",
    "PEER_WEIGHTED_RETURN",
)

HORIZONS = (
    90,
    180,
    365,
)

FEATURES = (
    "PRICE_ONLY",
    "PRICE_PLUS_AGE",
    "PRICE_PLUS_PATH_STABILITY",
)

TARGETS = (
    "RAW_PRICE_CHANGE",
    "LOG_PRICE_CHANGE",
    "RETURN",
    "ANNUALIZED_RETURN_WHERE_DEFINED",
)

MIN_PEERS = 5
NEIGHBOR_COUNT = 15


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_date(value: object) -> date:
    return date.fromisoformat(
        clean(value)[:10]
    )


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

        text = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    return list(
        csv.DictReader(
            text.splitlines()
        )
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
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def target_value(
    origin_price: float,
    endpoint_price: float,
    elapsed_days: int,
    target: str,
) -> float:

    if origin_price <= 0 or endpoint_price <= 0:
        raise ValueError(
            "nonpositive price"
        )

    if target == "RAW_PRICE_CHANGE":

        value = (
            endpoint_price
            - origin_price
        )

    elif target == "LOG_PRICE_CHANGE":

        value = math.log(
            endpoint_price
            / origin_price
        )

    elif target == "RETURN":

        value = (
            endpoint_price
            / origin_price
        ) - 1.0

    elif target == "ANNUALIZED_RETURN_WHERE_DEFINED":

        if elapsed_days <= 0:
            raise ValueError(
                "invalid elapsed days"
            )

        value = (
            (
                endpoint_price
                / origin_price
            )
            ** (
                365.0
                / float(elapsed_days)
            )
        ) - 1.0

    else:
        raise ValueError(
            f"unknown target {target}"
        )

    if not np.isfinite(value):
        raise ValueError(
            "nonfinite target"
        )

    return float(value)


def invert_target(
    origin_price: float,
    predicted_target: float,
    horizon: int,
    target: str,
) -> float:

    if target == "RAW_PRICE_CHANGE":

        value = (
            origin_price
            + predicted_target
        )

    elif target == "LOG_PRICE_CHANGE":

        value = (
            origin_price
            * math.exp(
                predicted_target
            )
        )

    elif target == "RETURN":

        value = (
            origin_price
            * (
                1.0
                + predicted_target
            )
        )

    elif target == "ANNUALIZED_RETURN_WHERE_DEFINED":

        base = (
            1.0
            + predicted_target
        )

        if base <= 0:
            raise ValueError(
                "annualized inversion base <= 0"
            )

        value = (
            origin_price
            * (
                base
                ** (
                    float(horizon)
                    / 365.0
                )
            )
        )

    else:
        raise ValueError(
            f"unknown target {target}"
        )

    if (
        not np.isfinite(value)
        or value <= 0
    ):
        raise ValueError(
            "invalid predicted price"
        )

    return float(value)


def feature_vector(
    feature: str,
    canonical_id: str,
    origin_date: date,
    history: dict[str, list[tuple[date, float]]],
    release_dates: dict[str, date],
) -> np.ndarray:

    observations = [
        item
        for item in history.get(
            canonical_id,
            [],
        )
        if item[0] <= origin_date
    ]

    if not observations:
        raise ValueError(
            "no history at origin"
        )

    origin_price = float(
        observations[-1][1]
    )

    values = [
        math.log(
            origin_price
        )
    ]

    if feature == "PRICE_ONLY":

        return np.asarray(
            values,
            dtype=float,
        )

    if feature == "PRICE_PLUS_AGE":

        if canonical_id not in release_dates:
            raise ValueError(
                "missing release date"
            )

        age_days = (
            origin_date
            - release_dates[
                canonical_id
            ]
        ).days

        if age_days < 0:
            raise ValueError(
                "origin before release"
            )

        return np.asarray(
            [
                *values,
                math.log1p(
                    age_days
                ),
            ],
            dtype=float,
        )

    if feature == "PRICE_PLUS_PATH_STABILITY":

        if len(observations) < 2:
            raise ValueError(
                "insufficient path history"
            )

        dates = [
            item[0]
            for item in observations
        ]

        prices = np.asarray(
            [
                item[1]
                for item in observations
            ],
            dtype=float,
        )

        log_prices = np.log(prices)

        standardized_returns = []

        for index in range(
            1,
            len(observations),
        ):

            elapsed = (
                dates[index]
                - dates[index - 1]
            ).days

            if elapsed <= 0:
                continue

            standardized_returns.append(
                (
                    log_prices[index]
                    - log_prices[index - 1]
                )
                / math.sqrt(
                    float(elapsed)
                )
            )

        if not standardized_returns:
            raise ValueError(
                "no valid path intervals"
            )

        volatility = float(
            np.std(
                standardized_returns,
                ddof=0,
            )
        )

        running_max = np.maximum.accumulate(
            prices
        )

        max_drawdown = float(
            abs(
                np.min(
                    (
                        prices
                        / running_max
                    ) - 1.0
                )
            )
        )

        first_date = dates[0]

        x = np.asarray(
            [
                (
                    observation_date
                    - first_date
                ).days
                for observation_date
                in dates
            ],
            dtype=float,
        )

        if np.ptp(x) <= 0:
            raise ValueError(
                "zero path span"
            )

        slope, _ = np.polyfit(
            x,
            log_prices,
            1,
        )

        result = np.asarray(
            [
                *values,
                volatility,
                max_drawdown,
                float(slope),
            ],
            dtype=float,
        )

        if not np.all(
            np.isfinite(result)
        ):
            raise ValueError(
                "nonfinite feature"
            )

        return result

    raise ValueError(
        f"unknown feature {feature}"
    )


def robust_scale(
    training: np.ndarray,
    validation: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:

    center = np.median(
        training,
        axis=0,
    )

    q75 = np.percentile(
        training,
        75,
        axis=0,
    )

    q25 = np.percentile(
        training,
        25,
        axis=0,
    )

    scale = q75 - q25

    std = np.std(
        training,
        axis=0,
    )

    scale = np.where(
        scale > 0,
        scale,
        np.where(
            std > 0,
            std,
            1.0,
        ),
    )

    return (
        (
            training
            - center
        )
        / scale,
        (
            validation
            - center
        )
        / scale,
    )


def error_values(
    origin_price: float,
    actual_price: float,
    predicted_price: float,
) -> dict[str, float]:

    error = predicted_price - actual_price

    absolute_error = abs(error)

    ape = (
        absolute_error
        / actual_price
    )

    denominator = (
        abs(predicted_price)
        + abs(actual_price)
    )

    smape = (
        0.0
        if denominator == 0
        else (
            2.0
            * absolute_error
            / denominator
        )
    )

    actual_return = (
        actual_price
        / origin_price
    ) - 1.0

    predicted_return = (
        predicted_price
        / origin_price
    ) - 1.0

    direction_correct = float(
        np.sign(actual_return)
        == np.sign(predicted_return)
    )

    downside_error = max(
        predicted_return
        - actual_return,
        0.0,
    )

    return {
        "error": float(error),
        "absolute_error": float(absolute_error),
        "squared_error": float(error * error),
        "ape": float(ape),
        "smape": float(smape),
        "actual_return": float(actual_return),
        "predicted_return": float(predicted_return),
        "direction_correct": direction_correct,
        "downside_error": float(downside_error),
    }


def safe_rank(rows) -> float | None:

    if len(rows) < 2:
        return None

    predicted = [
        float(
            row[
                "predicted_return"
            ]
        )
        for row in rows
    ]

    actual = [
        float(
            row[
                "actual_return"
            ]
        )
        for row in rows
    ]

    if (
        len(set(predicted)) < 2
        or len(set(actual)) < 2
    ):
        return None

    value = float(
        spearmanr(
            predicted,
            actual,
        ).statistic
    )

    if not np.isfinite(value):
        return None

    return value


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
        "--fold-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--matrix-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--runner-sha256",
        required=True,
    )

    parser.add_argument(
        "--contract-sha256",
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

    fold_rows_raw = read_zip_csv(
        args.fold_package,
        "precollector_temporal_fold_ledger_v1.csv",
    )

    matrix_rows = read_zip_csv(
        args.matrix_package,
        "precollector_executable_tournament_matrix_v1.csv",
    )

    if len(canonical_rows) != 131:
        fail("canonical count drift")

    if len(history_rows) != 3390:
        fail("history count drift")

    if len(fold_rows_raw) != 7803:
        fail("fold count drift")

    # ========================================================================
    # Release dates
    # ========================================================================

    release_column = None

    for candidate in (
        "release_date",
        "canonical_release_date",
        "resolved_release_date",
        "historical_release_date",
    ):

        if candidate in canonical_rows[0]:

            release_column = candidate
            break

    if release_column is None:

        fuzzy = [
            column
            for column in canonical_rows[0]
            if (
                "release" in column.lower()
                and "date" in column.lower()
            )
        ]

        if len(fuzzy) != 1:
            fail(
                "unable to resolve release date"
            )

        release_column = fuzzy[0]

    release_dates = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
        parse_date(
            row[
                release_column
            ]
        )
        for row in canonical_rows
    }

    # ========================================================================
    # History
    # ========================================================================

    history = defaultdict(list)

    for row in history_rows:

        history[
            clean(
                row[
                    "canonical_product_id"
                ]
            )
        ].append(
            (
                parse_date(
                    row[
                        "observation_date"
                    ]
                ),
                float(
                    row[
                        "historical_price"
                    ]
                ),
            )
        )

    for canonical_id in history:

        history[
            canonical_id
        ].sort(
            key=lambda item: item[0]
        )

    # ========================================================================
    # Folds
    # ========================================================================

    folds_by_horizon = defaultdict(list)
    validation_groups = defaultdict(list)

    for raw in fold_rows_raw:

        row = {
            "fold_id":
                clean(
                    raw[
                        "fold_id"
                    ]
                ),

            "canonical_product_id":
                clean(
                    raw[
                        "canonical_product_id"
                    ]
                ),

            "product_name":
                clean(
                    raw[
                        "product_name"
                    ]
                ),

            "horizon":
                int(
                    raw[
                        "requested_horizon_days"
                    ]
                ),

            "origin_date":
                parse_date(
                    raw[
                        "origin_date"
                    ]
                ),

            "origin_price":
                float(
                    raw[
                        "origin_price"
                    ]
                ),

            "endpoint_date":
                parse_date(
                    raw[
                        "realized_endpoint_date"
                    ]
                ),

            "endpoint_price":
                float(
                    raw[
                        "realized_endpoint_price"
                    ]
                ),

            "actual_elapsed_days":
                int(
                    raw[
                        "actual_elapsed_days"
                    ]
                ),
        }

        if row["horizon"] not in HORIZONS:
            fail(
                "unexpected fold horizon"
            )

        folds_by_horizon[
            row[
                "horizon"
            ]
        ].append(row)

        validation_groups[
            (
                row[
                    "horizon"
                ],
                row[
                    "origin_date"
                ],
            )
        ].append(row)

    # ========================================================================
    # Matrix
    # ========================================================================

    cells = []
    cell_lookup = {}

    for row in matrix_rows:

        if (
            clean(
                row[
                    "direct_oos_authorized"
                ]
            ).lower()
            != "true"
        ):
            continue

        model = clean(
            row[
                "model_family"
            ]
        )

        if model not in MODELS:
            continue

        cell = {
            "combination_id":
                clean(
                    row[
                        "combination_id"
                    ]
                ),

            "model_family":
                model,

            "feature_variant":
                clean(
                    row[
                        "feature_variant"
                    ]
                ),

            "target_transformation":
                clean(
                    row[
                        "target_transformation"
                    ]
                ),

            "requested_horizon_days":
                int(
                    row[
                        "requested_horizon_days"
                    ]
                ),
        }

        cells.append(cell)

        cell_lookup[
            (
                cell[
                    "model_family"
                ],
                cell[
                    "feature_variant"
                ],
                cell[
                    "target_transformation"
                ],
                cell[
                    "requested_horizon_days"
                ],
            )
        ] = cell[
            "combination_id"
        ]

    if len(cells) != 72:
        fail(
            f"expected 72 peer cells, got {len(cells)}"
        )

    # ========================================================================
    # Feature cache
    # ========================================================================

    feature_cache = {}

    def get_feature(
        feature,
        canonical_id,
        origin_date,
    ):

        key = (
            feature,
            canonical_id,
            origin_date,
        )

        if key in feature_cache:

            value = feature_cache[key]

            if isinstance(
                value,
                Exception,
            ):
                raise value

            return value

        try:

            result = feature_vector(
                feature,
                canonical_id,
                origin_date,
                history,
                release_dates,
            )

            feature_cache[key] = result

            return result

        except Exception as exc:

            stored = ValueError(
                str(exc)
            )

            feature_cache[key] = stored

            raise stored

    # ========================================================================
    # Execution
    # ========================================================================

    predictions = []
    skipped = []
    peer_group_ledger = []

    total_groups = (
        len(validation_groups)
        * len(FEATURES)
        * len(TARGETS)
        * len(MODELS)
    )

    completed_groups = 0

    for model in MODELS:

        print(
            f"START_MODEL={model}",
            flush=True,
        )

        prediction_start = len(predictions)
        skip_start = len(skipped)

        for (
            horizon,
            validation_origin,
        ), validation_folds in sorted(
            validation_groups.items(),
            key=lambda item: (
                item[0][0],
                item[0][1],
            ),
        ):

            matured = [
                fold
                for fold in folds_by_horizon[
                    horizon
                ]
                if (
                    fold[
                        "endpoint_date"
                    ]
                    <= validation_origin
                )
            ]

            for feature in FEATURES:

                train_features = []
                valid_train_folds = []

                if model == "PEER_WEIGHTED_RETURN":

                    for train_fold in matured:

                        try:

                            vector = get_feature(
                                feature,
                                train_fold[
                                    "canonical_product_id"
                                ],
                                train_fold[
                                    "origin_date"
                                ],
                            )

                        except Exception:
                            continue

                        train_features.append(
                            vector
                        )

                        valid_train_folds.append(
                            train_fold
                        )

                else:

                    valid_train_folds = list(
                        matured
                    )

                for target in TARGETS:

                    completed_groups += 1

                    combination_id = cell_lookup[
                        (
                            model,
                            feature,
                            target,
                            horizon,
                        )
                    ]

                    train_targets = []
                    target_train_folds = []
                    target_train_features = []

                    for index, train_fold in enumerate(
                        valid_train_folds
                    ):

                        try:

                            value = target_value(
                                train_fold[
                                    "origin_price"
                                ],
                                train_fold[
                                    "endpoint_price"
                                ],
                                train_fold[
                                    "actual_elapsed_days"
                                ],
                                target,
                            )

                        except Exception:
                            continue

                        train_targets.append(
                            value
                        )

                        target_train_folds.append(
                            train_fold
                        )

                        if model == "PEER_WEIGHTED_RETURN":

                            target_train_features.append(
                                train_features[index]
                            )

                    peer_group_ledger.append(
                        {
                            "model_family":
                                model,

                            "feature_variant":
                                feature,

                            "target_transformation":
                                target,

                            "requested_horizon_days":
                                horizon,

                            "validation_origin":
                                validation_origin.isoformat(),

                            "available_peer_rows":
                                len(train_targets),

                            "group_status":
                                (
                                    "AVAILABLE"
                                    if len(train_targets) >= MIN_PEERS
                                    else "INSUFFICIENT_PEERS"
                                ),
                        }
                    )

                    if len(train_targets) < MIN_PEERS:

                        for fold in validation_folds:

                            skipped.append(
                                {
                                    "combination_id":
                                        combination_id,

                                    "model_family":
                                        model,

                                    "feature_variant":
                                        feature,

                                    "target_transformation":
                                        target,

                                    "requested_horizon_days":
                                        horizon,

                                    "fold_id":
                                        fold[
                                            "fold_id"
                                        ],

                                    "canonical_product_id":
                                        fold[
                                            "canonical_product_id"
                                        ],

                                    "origin_date":
                                        fold[
                                            "origin_date"
                                        ].isoformat(),

                                    "skip_reason":
                                        (
                                            "INSUFFICIENT_MATURED_PEERS:"
                                            f"{len(train_targets)}"
                                        ),
                                }
                            )

                        continue

                    y_train = np.asarray(
                        train_targets,
                        dtype=float,
                    )

                    if model == "PEER_MEDIAN_RETURN":

                        predicted_target = float(
                            np.median(
                                y_train
                            )
                        )

                        for fold in validation_folds:

                            try:

                                predicted_price = invert_target(
                                    fold[
                                        "origin_price"
                                    ],
                                    predicted_target,
                                    horizon,
                                    target,
                                )

                                metrics = error_values(
                                    fold[
                                        "origin_price"
                                    ],
                                    fold[
                                        "endpoint_price"
                                    ],
                                    predicted_price,
                                )

                            except Exception as exc:

                                skipped.append(
                                    {
                                        "combination_id":
                                            combination_id,

                                        "model_family":
                                            model,

                                        "feature_variant":
                                            feature,

                                        "target_transformation":
                                            target,

                                        "requested_horizon_days":
                                            horizon,

                                        "fold_id":
                                            fold[
                                                "fold_id"
                                            ],

                                        "canonical_product_id":
                                            fold[
                                                "canonical_product_id"
                                            ],

                                        "origin_date":
                                            fold[
                                                "origin_date"
                                            ].isoformat(),

                                        "skip_reason":
                                            (
                                                "PEER_MEDIAN_FAILURE:"
                                                + str(exc)
                                            ),
                                    }
                                )

                                continue

                            predictions.append(
                                {
                                    "combination_id":
                                        combination_id,

                                    "semantic_model_key":
                                        (
                                            f"{model}|"
                                            f"{target}|"
                                            f"H{horizon}"
                                        ),

                                    "model_family":
                                        model,

                                    "feature_variant":
                                        feature,

                                    "target_transformation":
                                        target,

                                    "requested_horizon_days":
                                        horizon,

                                    "fold_id":
                                        fold[
                                            "fold_id"
                                        ],

                                    "canonical_product_id":
                                        fold[
                                            "canonical_product_id"
                                        ],

                                    "product_name":
                                        fold[
                                            "product_name"
                                        ],

                                    "origin_date":
                                        fold[
                                            "origin_date"
                                        ].isoformat(),

                                    "origin_price":
                                        fold[
                                            "origin_price"
                                        ],

                                    "realized_endpoint_date":
                                        fold[
                                            "endpoint_date"
                                        ].isoformat(),

                                    "actual_endpoint_price":
                                        fold[
                                            "endpoint_price"
                                        ],

                                    "predicted_endpoint_price":
                                        predicted_price,

                                    "available_peer_rows":
                                        len(train_targets),

                                    "selected_peer_rows":
                                        len(train_targets),

                                    **metrics,
                                }
                            )

                        continue

                    # ========================================================
                    # Weighted peer transfer
                    # ========================================================

                    X_train = np.vstack(
                        target_train_features
                    )

                    for fold in validation_folds:

                        try:

                            x_validation = get_feature(
                                feature,
                                fold[
                                    "canonical_product_id"
                                ],
                                fold[
                                    "origin_date"
                                ],
                            )

                            (
                                X_scaled,
                                validation_scaled,
                            ) = robust_scale(
                                X_train,
                                x_validation.reshape(
                                    1,
                                    -1,
                                ),
                            )

                            distances = np.sqrt(
                                np.sum(
                                    (
                                        X_scaled
                                        - validation_scaled[0]
                                    )
                                    ** 2,
                                    axis=1,
                                )
                            )

                            count = min(
                                NEIGHBOR_COUNT,
                                len(distances),
                            )

                            indices = np.argsort(
                                distances
                            )[:count]

                            selected_distances = (
                                distances[
                                    indices
                                ]
                            )

                            selected_targets = (
                                y_train[
                                    indices
                                ]
                            )

                            weights = (
                                1.0
                                / (
                                    1.0
                                    + selected_distances
                                )
                            )

                            if (
                                not np.all(
                                    np.isfinite(weights)
                                )
                                or float(
                                    np.sum(weights)
                                )
                                <= 0
                            ):
                                raise ValueError(
                                    "invalid peer weights"
                                )

                            predicted_target = float(
                                np.average(
                                    selected_targets,
                                    weights=weights,
                                )
                            )

                            predicted_price = invert_target(
                                fold[
                                    "origin_price"
                                ],
                                predicted_target,
                                horizon,
                                target,
                            )

                            metrics = error_values(
                                fold[
                                    "origin_price"
                                ],
                                fold[
                                    "endpoint_price"
                                ],
                                predicted_price,
                            )

                        except Exception as exc:

                            skipped.append(
                                {
                                    "combination_id":
                                        combination_id,

                                    "model_family":
                                        model,

                                    "feature_variant":
                                        feature,

                                    "target_transformation":
                                        target,

                                    "requested_horizon_days":
                                        horizon,

                                    "fold_id":
                                        fold[
                                            "fold_id"
                                        ],

                                    "canonical_product_id":
                                        fold[
                                            "canonical_product_id"
                                        ],

                                    "origin_date":
                                        fold[
                                            "origin_date"
                                        ].isoformat(),

                                    "skip_reason":
                                        (
                                            "PEER_WEIGHTED_FAILURE:"
                                            + str(exc)
                                        ),
                                }
                            )

                            continue

                        predictions.append(
                            {
                                "combination_id":
                                    combination_id,

                                "semantic_model_key":
                                    (
                                        f"{model}|"
                                        f"{feature}|"
                                        f"{target}|"
                                        f"H{horizon}"
                                    ),

                                "model_family":
                                    model,

                                "feature_variant":
                                    feature,

                                "target_transformation":
                                    target,

                                "requested_horizon_days":
                                    horizon,

                                "fold_id":
                                    fold[
                                        "fold_id"
                                    ],

                                "canonical_product_id":
                                    fold[
                                        "canonical_product_id"
                                    ],

                                "product_name":
                                    fold[
                                        "product_name"
                                    ],

                                "origin_date":
                                    fold[
                                        "origin_date"
                                    ].isoformat(),

                                "origin_price":
                                    fold[
                                        "origin_price"
                                    ],

                                "realized_endpoint_date":
                                    fold[
                                        "endpoint_date"
                                    ].isoformat(),

                                "actual_endpoint_price":
                                    fold[
                                        "endpoint_price"
                                    ],

                                "predicted_endpoint_price":
                                    predicted_price,

                                "available_peer_rows":
                                    len(train_targets),

                                "selected_peer_rows":
                                    count,

                                **metrics,
                            }
                        )

        print(
            (
                f"COMPLETE_MODEL={model}"
                f"|PREDICTIONS={len(predictions) - prediction_start}"
                f"|SKIPS={len(skipped) - skip_start}"
                f"|PROGRESS_GROUPS={completed_groups}/{total_groups}"
            ),
            flush=True,
        )

    if not predictions:
        fail(
            "no peer predictions generated"
        )

    # ========================================================================
    # Cell scorecard
    # ========================================================================

    groups = defaultdict(list)
    skips_by_cell = defaultdict(int)

    for row in predictions:

        groups[
            row[
                "combination_id"
            ]
        ].append(row)

    for row in skipped:

        skips_by_cell[
            row[
                "combination_id"
            ]
        ] += 1

    cell_by_id = {
        cell[
            "combination_id"
        ]: cell
        for cell in cells
    }

    scorecard = []

    for combination_id in sorted(
        cell_by_id
    ):

        cell = cell_by_id[
            combination_id
        ]

        rows = groups.get(
            combination_id,
            [],
        )

        if not rows:

            scorecard.append(
                {
                    **cell,
                    "semantic_model_key": "",
                    "prediction_rows": 0,
                    "skipped_rows":
                        skips_by_cell[
                            combination_id
                        ],
                    "product_count": 0,
                    "origin_count": 0,
                    "SMAPE": "",
                    "MAE": "",
                    "RMSE": "",
                    "MEDIAN_APE": "",
                    "BIAS": "",
                    "DIRECTIONAL_ACCURACY": "",
                    "DOWNSIDE_ERROR": "",
                    "RANK_CORRELATION": "",
                }
            )

            continue

        by_origin = defaultdict(list)

        for row in rows:

            by_origin[
                row[
                    "origin_date"
                ]
            ].append(row)

        ranks = []

        for origin_rows in by_origin.values():

            rank = safe_rank(
                origin_rows
            )

            if rank is not None:
                ranks.append(rank)

        scorecard.append(
            {
                **cell,

                "semantic_model_key":
                    rows[0][
                        "semantic_model_key"
                    ],

                "prediction_rows":
                    len(rows),

                "skipped_rows":
                    skips_by_cell[
                        combination_id
                    ],

                "product_count":
                    len(
                        {
                            row[
                                "canonical_product_id"
                            ]
                            for row in rows
                        }
                    ),

                "origin_count":
                    len(by_origin),

                "SMAPE":
                    float(
                        np.mean(
                            [
                                row[
                                    "smape"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "MAE":
                    float(
                        np.mean(
                            [
                                row[
                                    "absolute_error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "RMSE":
                    float(
                        math.sqrt(
                            np.mean(
                                [
                                    row[
                                        "squared_error"
                                    ]
                                    for row in rows
                                ]
                            )
                        )
                    ),

                "MEDIAN_APE":
                    float(
                        np.median(
                            [
                                row[
                                    "ape"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "BIAS":
                    float(
                        np.mean(
                            [
                                row[
                                    "error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "DIRECTIONAL_ACCURACY":
                    float(
                        np.mean(
                            [
                                row[
                                    "direction_correct"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "DOWNSIDE_ERROR":
                    float(
                        np.mean(
                            [
                                row[
                                    "downside_error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "RANK_CORRELATION":
                    (
                        ""
                        if not ranks
                        else float(
                            np.mean(ranks)
                        )
                    ),
            }
        )

    if len(scorecard) != 72:
        fail(
            "peer scorecard must contain 72 cells"
        )

    # ========================================================================
    # Product error ledger
    # ========================================================================

    product_groups = defaultdict(list)

    for row in predictions:

        product_groups[
            (
                row[
                    "combination_id"
                ],
                row[
                    "canonical_product_id"
                ],
                row[
                    "product_name"
                ],
            )
        ].append(row)

    product_rows = []

    for (
        combination_id,
        canonical_id,
        product_name,
    ), rows in sorted(
        product_groups.items()
    ):

        product_rows.append(
            {
                "combination_id":
                    combination_id,

                "model_family":
                    rows[0][
                        "model_family"
                    ],

                "feature_variant":
                    rows[0][
                        "feature_variant"
                    ],

                "target_transformation":
                    rows[0][
                        "target_transformation"
                    ],

                "requested_horizon_days":
                    rows[0][
                        "requested_horizon_days"
                    ],

                "canonical_product_id":
                    canonical_id,

                "product_name":
                    product_name,

                "prediction_rows":
                    len(rows),

                "SMAPE":
                    float(
                        np.mean(
                            [
                                row[
                                    "smape"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "MAE":
                    float(
                        np.mean(
                            [
                                row[
                                    "absolute_error"
                                ]
                                for row in rows
                            ]
                        )
                    ),

                "BIAS":
                    float(
                        np.mean(
                            [
                                row[
                                    "error"
                                ]
                                for row in rows
                            ]
                        )
                    ),
            }
        )

    # ========================================================================
    # Descriptive lowest by horizon
    # ========================================================================

    descriptive = {}

    for horizon in HORIZONS:

        candidates = [
            row
            for row in scorecard
            if (
                row[
                    "requested_horizon_days"
                ]
                == horizon
                and row[
                    "SMAPE"
                ]
                != ""
            )
        ]

        if not candidates:
            continue

        best = min(
            candidates,
            key=lambda row: float(
                row[
                    "SMAPE"
                ]
            ),
        )

        descriptive[
            str(horizon)
        ] = {
            "combination_id":
                best[
                    "combination_id"
                ],

            "model_family":
                best[
                    "model_family"
                ],

            "feature_variant":
                best[
                    "feature_variant"
                ],

            "target_transformation":
                best[
                    "target_transformation"
                ],

            "SMAPE":
                best[
                    "SMAPE"
                ],

            "status":
                "DESCRIPTIVE_BATCH_RESULT_NOT_CERTIFIED_WINNER",
        }

    # ========================================================================
    # Outputs
    # ========================================================================

    root = args.output_root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    prediction_path = (
        root
        / "precollector_15wc_prediction_ledger_v1.csv"
    )

    scorecard_path = (
        root
        / "precollector_15wc_cell_scorecard_v1.csv"
    )

    peer_group_path = (
        root
        / "precollector_15wc_peer_group_ledger_v1.csv"
    )

    product_path = (
        root
        / "precollector_15wc_product_oos_error_ledger_v1.csv"
    )

    skipped_path = (
        root
        / "precollector_15wc_skipped_fold_ledger_v1.csv"
    )

    summary_path = (
        root
        / "precollector_15wc_summary_v1.json"
    )

    manifest_path = (
        root
        / "precollector_15wc_manifest_v1.json"
    )

    write_csv(
        prediction_path,
        predictions,
        [
            "combination_id",
            "semantic_model_key",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "fold_id",
            "canonical_product_id",
            "product_name",
            "origin_date",
            "origin_price",
            "realized_endpoint_date",
            "actual_endpoint_price",
            "predicted_endpoint_price",
            "available_peer_rows",
            "selected_peer_rows",
            "error",
            "absolute_error",
            "squared_error",
            "ape",
            "smape",
            "actual_return",
            "predicted_return",
            "direction_correct",
            "downside_error",
        ],
    )

    write_csv(
        scorecard_path,
        scorecard,
        [
            "combination_id",
            "semantic_model_key",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "prediction_rows",
            "skipped_rows",
            "product_count",
            "origin_count",
            "SMAPE",
            "MAE",
            "RMSE",
            "MEDIAN_APE",
            "BIAS",
            "DIRECTIONAL_ACCURACY",
            "DOWNSIDE_ERROR",
            "RANK_CORRELATION",
        ],
    )

    write_csv(
        peer_group_path,
        peer_group_ledger,
        [
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "validation_origin",
            "available_peer_rows",
            "group_status",
        ],
    )

    write_csv(
        product_path,
        product_rows,
        [
            "combination_id",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "canonical_product_id",
            "product_name",
            "prediction_rows",
            "SMAPE",
            "MAE",
            "BIAS",
        ],
    )

    write_csv(
        skipped_path,
        skipped,
        [
            "combination_id",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "fold_id",
            "canonical_product_id",
            "origin_date",
            "skip_reason",
        ],
    )

    insufficient_groups = sum(
        1
        for row in peer_group_ledger
        if (
            row[
                "group_status"
            ]
            == "INSUFFICIENT_PEERS"
        )
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_C",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "batch_id":
            "15W-C",

        "models_executed":
            list(MODELS),

        "model_count":
            2,

        "governed_matrix_cells":
            len(scorecard),

        "prediction_rows":
            len(predictions),

        "skipped_rows":
            len(skipped),

        "peer_group_rows":
            len(peer_group_ledger),

        "insufficient_peer_groups":
            insufficient_groups,

        "descriptive_lowest_smape":
            descriptive,

        "certified_winner_selected":
            False,

        "product_holdout_executed":
            False,

        "product_treatments_assigned":
            0,

        "product_exclusions_assigned":
            0,

        "production_model_selection_authorized":
            False,

        "monte_carlo_execution_authorized":
            False,

        "forecast_execution_authorized":
            False,

        "ranking_execution_authorized":
            False,

        "purchase_analysis_authorized":
            False,

        "authorized_next_stage":
            "RUN_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_D",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    members = [
        prediction_path,
        scorecard_path,
        peer_group_path,
        product_path,
        skipped_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_15wc_manifest_v1",

        "runner_sha256_pre_execution":
            args.runner_sha256,

        "contract_sha256_pre_execution":
            args.contract_sha256,

        "members": [
            {
                "file_name":
                    path.name,

                "sha256":
                    sha256_file(path),

                "byte_length":
                    path.stat().st_size,
            }
            for path in members
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
        "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_C"
    )

    print(
        "MODELS_EXECUTED=2"
    )

    print(
        "GOVERNED_MATRIX_CELLS=72"
    )

    print(
        f"PREDICTION_ROWS={len(predictions)}"
    )

    print(
        f"SKIPPED_ROWS={len(skipped)}"
    )

    print(
        f"PEER_GROUP_ROWS={len(peer_group_ledger)}"
    )

    print(
        f"INSUFFICIENT_PEER_GROUPS={insufficient_groups}"
    )

    for horizon in HORIZONS:

        best = descriptive.get(
            str(horizon)
        )

        if best:

            print(
                (
                    f"HORIZON_{horizon}_LOWEST_15WC_SMAPE="
                    f"{best['combination_id']}|"
                    f"{best['model_family']}|"
                    f"{best['feature_variant']}|"
                    f"{best['target_transformation']}|"
                    f"{float(best['SMAPE']):.8f}"
                )
            )

    print(
        "CERTIFIED_WINNER_SELECTED=FALSE"
    )

    print(
        "PRODUCT_HOLDOUT_EXECUTED=FALSE"
    )

    print(
        "PRODUCT_EXCLUSIONS_ASSIGNED=0"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())