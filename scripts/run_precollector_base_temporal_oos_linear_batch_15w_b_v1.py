from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import warnings
import zipfile

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from scipy.stats import spearmanr

from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


MODELS = (
    "RIDGE_REGRESSION",
    "HUBER_REGRESSION",
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

MIN_TRAINING_ROWS = 20


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
    actual_elapsed_days: int,
    target: str,
) -> float:

    if origin_price <= 0 or endpoint_price <= 0:
        raise ValueError(
            "nonpositive target price"
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

        if actual_elapsed_days <= 0:
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
                / float(
                    actual_elapsed_days
                )
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

    if not np.isfinite(
        predicted_target
    ):
        raise ValueError(
            "nonfinite predicted target"
        )

    if target == "RAW_PRICE_CHANGE":

        price = (
            origin_price
            + predicted_target
        )

    elif target == "LOG_PRICE_CHANGE":

        price = (
            origin_price
            * math.exp(
                predicted_target
            )
        )

    elif target == "RETURN":

        price = (
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

        price = (
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
        not np.isfinite(price)
        or price <= 0
    ):
        raise ValueError(
            "invalid predicted price"
        )

    return float(price)


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

    if origin_price <= 0:
        raise ValueError(
            "invalid origin price"
        )

    base = [
        math.log(
            origin_price
        )
    ]

    if feature == "PRICE_ONLY":

        return np.asarray(
            base,
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
                *base,
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

        log_prices = np.log(
            prices
        )

        interval_returns = []

        for index in range(
            1,
            len(observations),
        ):

            elapsed = (
                dates[index]
                - dates[
                    index - 1
                ]
            ).days

            if elapsed <= 0:
                continue

            interval_returns.append(
                (
                    log_prices[index]
                    - log_prices[
                        index - 1
                    ]
                )
                / math.sqrt(
                    float(elapsed)
                )
            )

        if not interval_returns:
            raise ValueError(
                "no valid path intervals"
            )

        volatility = float(
            np.std(
                interval_returns,
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
                    obs_date
                    - first_date
                ).days
                for obs_date
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
                *base,
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


def estimator_for(model: str):

    if model == "RIDGE_REGRESSION":

        return Pipeline(
            [
                (
                    "scale",
                    StandardScaler(),
                ),
                (
                    "model",
                    Ridge(
                        alpha=1.0,
                        fit_intercept=True,
                    ),
                ),
            ]
        )

    if model == "HUBER_REGRESSION":

        return Pipeline(
            [
                (
                    "scale",
                    StandardScaler(),
                ),
                (
                    "model",
                    HuberRegressor(
                        epsilon=1.35,
                        alpha=0.0001,
                        max_iter=1000,
                    ),
                ),
            ]
        )

    raise ValueError(
        f"unknown model {model}"
    )


def error_values(
    origin_price: float,
    actual_price: float,
    predicted_price: float,
) -> dict[str, float]:

    error = (
        predicted_price
        - actual_price
    )

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


def safe_rank(
    rows: list[dict[str, object]],
) -> float | None:

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

    # ------------------------------------------------------------------------
    # Resolve release-date column
    # ------------------------------------------------------------------------

    release_candidates = (
        "release_date",
        "canonical_release_date",
        "resolved_release_date",
        "historical_release_date",
    )

    release_column = None

    for candidate in release_candidates:

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
                "unable to resolve release date column"
            )

        release_column = fuzzy[0]

    release_dates = {}

    for row in canonical_rows:

        canonical_id = clean(
            row[
                "canonical_product_id"
            ]
        )

        release_dates[
            canonical_id
        ] = parse_date(
            row[
                release_column
            ]
        )

    # ------------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Folds
    # ------------------------------------------------------------------------

    folds = []

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
                "unexpected horizon in fold ledger"
            )

        folds.append(row)

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

    # ------------------------------------------------------------------------
    # Matrix cells
    # ------------------------------------------------------------------------

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
            f"expected 72 cells, got {len(cells)}"
        )

    # ------------------------------------------------------------------------
    # Point-in-time feature cache
    # ------------------------------------------------------------------------

    feature_cache = {}

    def get_feature(
        feature: str,
        canonical_id: str,
        origin_date: date,
    ) -> np.ndarray:

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

    predictions = []
    skipped = []
    fit_ledger = []

    total_groups = (
        len(
            validation_groups
        )
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

        model_prediction_start = len(
            predictions
        )

        model_skip_start = len(
            skipped
        )

        model_fit_start = len(
            fit_ledger
        )

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

                validation_features = {}
                validation_feature_errors = {}

                for fold in validation_folds:

                    try:

                        validation_features[
                            fold[
                                "fold_id"
                            ]
                        ] = get_feature(
                            feature,
                            fold[
                                "canonical_product_id"
                            ],
                            fold[
                                "origin_date"
                            ],
                        )

                    except Exception as exc:

                        validation_feature_errors[
                            fold[
                                "fold_id"
                            ]
                        ] = str(exc)

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

                    train_x = []
                    train_y = []

                    for train_fold in matured:

                        try:

                            x = get_feature(
                                feature,
                                train_fold[
                                    "canonical_product_id"
                                ],
                                train_fold[
                                    "origin_date"
                                ],
                            )

                            y = target_value(
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

                        train_x.append(x)
                        train_y.append(y)

                    if len(train_x) < MIN_TRAINING_ROWS:

                        fit_ledger.append(
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

                                "training_rows":
                                    len(train_x),

                                "fit_status":
                                    "SKIPPED_INSUFFICIENT_TRAINING_ROWS",

                                "fit_warning":
                                    "",
                            }
                        )

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
                                            "INSUFFICIENT_MATURED_TRAINING_ROWS:"
                                            f"{len(train_x)}"
                                        ),
                                }
                            )

                        continue

                    X_train = np.vstack(
                        train_x
                    )

                    y_train = np.asarray(
                        train_y,
                        dtype=float,
                    )

                    estimator = estimator_for(
                        model
                    )

                    fit_warning = ""

                    try:

                        with warnings.catch_warnings(
                            record=True
                        ) as caught:

                            warnings.simplefilter(
                                "always",
                                ConvergenceWarning,
                            )

                            estimator.fit(
                                X_train,
                                y_train,
                            )

                            convergence_messages = [
                                str(
                                    warning.message
                                )
                                for warning in caught
                                if issubclass(
                                    warning.category,
                                    ConvergenceWarning,
                                )
                            ]

                            if convergence_messages:

                                fit_warning = (
                                    " | ".join(
                                        convergence_messages
                                    )
                                )

                    except Exception as exc:

                        fit_ledger.append(
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

                                "training_rows":
                                    len(train_x),

                                "fit_status":
                                    "FIT_FAILURE",

                                "fit_warning":
                                    str(exc),
                            }
                        )

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
                                            "MODEL_FIT_FAILURE:"
                                            + str(exc)
                                        ),
                                }
                            )

                        continue

                    fit_ledger.append(
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

                            "training_rows":
                                len(train_x),

                            "fit_status":
                                "FIT_SUCCESS",

                            "fit_warning":
                                fit_warning,
                        }
                    )

                    for fold in validation_folds:

                        fold_id = fold[
                            "fold_id"
                        ]

                        if (
                            fold_id
                            in validation_feature_errors
                        ):

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
                                        fold_id,

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
                                            "VALIDATION_FEATURE_UNAVAILABLE:"
                                            + validation_feature_errors[
                                                fold_id
                                            ]
                                        ),
                                }
                            )

                            continue

                        try:

                            predicted_target = float(
                                estimator.predict(
                                    validation_features[
                                        fold_id
                                    ].reshape(
                                        1,
                                        -1,
                                    )
                                )[0]
                            )

                            predicted_price = invert_target(
                                fold[
                                    "origin_price"
                                ],
                                predicted_target,
                                horizon,
                                target,
                            )

                            row_errors = error_values(
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
                                        fold_id,

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
                                            "PREDICTION_FAILURE:"
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
                                    fold_id,

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

                                **row_errors,
                            }
                        )

        print(
            (
                f"COMPLETE_MODEL={model}"
                f"|PREDICTIONS={len(predictions) - model_prediction_start}"
                f"|SKIPS={len(skipped) - model_skip_start}"
                f"|FIT_ROWS={len(fit_ledger) - model_fit_start}"
                f"|PROGRESS_GROUPS={completed_groups}/{total_groups}"
            ),
            flush=True,
        )

    if not predictions:
        fail(
            "no Ridge/Huber predictions generated"
        )

    # ========================================================================
    # Cell scorecards
    # ========================================================================

    prediction_groups = defaultdict(
        list
    )

    skipped_by_cell = defaultdict(
        int
    )

    for row in predictions:

        prediction_groups[
            row[
                "combination_id"
            ]
        ].append(row)

    for row in skipped:

        skipped_by_cell[
            row[
                "combination_id"
            ]
        ] += 1

    cell_by_id = {
        row[
            "combination_id"
        ]: row
        for row in cells
    }

    scorecard = []

    for combination_id in sorted(
        cell_by_id
    ):

        cell = cell_by_id[
            combination_id
        ]

        rows = prediction_groups.get(
            combination_id,
            [],
        )

        if not rows:

            scorecard.append(
                {
                    **cell,
                    "prediction_rows": 0,
                    "skipped_rows":
                        skipped_by_cell[
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

        by_origin = defaultdict(
            list
        )

        for row in rows:

            by_origin[
                row[
                    "origin_date"
                ]
            ].append(row)

        rank_values = []

        for origin_rows in by_origin.values():

            rank = safe_rank(
                origin_rows
            )

            if rank is not None:
                rank_values.append(rank)

        scorecard.append(
            {
                **cell,

                "prediction_rows":
                    len(rows),

                "skipped_rows":
                    skipped_by_cell[
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
                        if not rank_values
                        else float(
                            np.mean(
                                rank_values
                            )
                        )
                    ),
            }
        )

    if len(scorecard) != 72:
        fail(
            f"scorecard rows={len(scorecard)}, expected 72"
        )

    # ========================================================================
    # Product-level error ledger
    # ========================================================================

    product_groups = defaultdict(
        list
    )

    for row in predictions:

        product_groups[
            (
                row[
                    "combination_id"
                ],
                row[
                    "model_family"
                ],
                row[
                    "feature_variant"
                ],
                row[
                    "target_transformation"
                ],
                row[
                    "requested_horizon_days"
                ],
                row[
                    "canonical_product_id"
                ],
                row[
                    "product_name"
                ],
            )
        ].append(row)

    product_error_rows = []

    for key, rows in sorted(
        product_groups.items()
    ):

        (
            combination_id,
            model,
            feature,
            target,
            horizon,
            canonical_id,
            product_name,
        ) = key

        product_error_rows.append(
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
    # Descriptive lowest SMAPE by horizon
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
    # Write governed outputs
    # ========================================================================

    root = args.output_root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    prediction_path = (
        root
        / "precollector_15wb_prediction_ledger_v1.csv"
    )

    scorecard_path = (
        root
        / "precollector_15wb_cell_scorecard_v1.csv"
    )

    fit_path = (
        root
        / "precollector_15wb_fit_ledger_v1.csv"
    )

    product_path = (
        root
        / "precollector_15wb_product_oos_error_ledger_v1.csv"
    )

    skipped_path = (
        root
        / "precollector_15wb_skipped_fold_ledger_v1.csv"
    )

    summary_path = (
        root
        / "precollector_15wb_summary_v1.json"
    )

    manifest_path = (
        root
        / "precollector_15wb_manifest_v1.json"
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
        fit_path,
        fit_ledger,
        [
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "validation_origin",
            "training_rows",
            "fit_status",
            "fit_warning",
        ],
    )

    write_csv(
        product_path,
        product_error_rows,
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

    successful_fits = sum(
        1
        for row in fit_ledger
        if (
            row[
                "fit_status"
            ]
            == "FIT_SUCCESS"
        )
    )

    failed_fits = sum(
        1
        for row in fit_ledger
        if (
            row[
                "fit_status"
            ]
            == "FIT_FAILURE"
        )
    )

    insufficient_fits = sum(
        1
        for row in fit_ledger
        if (
            row[
                "fit_status"
            ]
            == "SKIPPED_INSUFFICIENT_TRAINING_ROWS"
        )
    )

    convergence_warning_fits = sum(
        1
        for row in fit_ledger
        if clean(
            row[
                "fit_warning"
            ]
        )
    )

    summary = {
        "status":
            "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_B",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "batch_id":
            "15W-B",

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

        "fit_ledger_rows":
            len(fit_ledger),

        "successful_fits":
            successful_fits,

        "fit_failures":
            failed_fits,

        "insufficient_training_fit_groups":
            insufficient_fits,

        "fit_groups_with_convergence_warning":
            convergence_warning_fits,

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
            "RUN_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_C",
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
        fit_path,
        product_path,
        skipped_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_15wb_manifest_v1",

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
        "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_B"
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
        f"SUCCESSFUL_FITS={successful_fits}"
    )

    print(
        f"FIT_FAILURES={failed_fits}"
    )

    print(
        "INSUFFICIENT_TRAINING_FIT_GROUPS="
        f"{insufficient_fits}"
    )

    print(
        "FIT_GROUPS_WITH_CONVERGENCE_WARNING="
        f"{convergence_warning_fits}"
    )

    for horizon in HORIZONS:

        best = descriptive.get(
            str(horizon)
        )

        if best:

            print(
                (
                    f"HORIZON_{horizon}_LOWEST_15WB_SMAPE="
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