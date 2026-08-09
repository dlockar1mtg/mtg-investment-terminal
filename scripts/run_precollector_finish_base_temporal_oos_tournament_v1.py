from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
import zipfile

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from scipy.stats import spearmanr

from sklearn.ensemble import (
    GradientBoostingRegressor,
    RandomForestRegressor,
)


TREE_MODELS = (
    "RANDOM_FOREST",
    "GRADIENT_BOOSTING",
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

EXPECTED_BASE_CELLS = 396
EXPECTED_TREE_CELLS = 72


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
                f"missing ZIP member {member} "
                f"in {package.name}"
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

        for row in rows:
            writer.writerow(row)


def atomic_json_write(
    path: Path,
    payload: dict,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="checkpoint_",
        suffix=".json.tmp",
        dir=str(
            path.parent
        ),
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:

            json.dump(
                payload,
                handle,
                separators=(",", ":"),
            )

            handle.flush()
            os.fsync(
                handle.fileno()
            )

        os.replace(
            temp_name,
            path,
        )

    except Exception:

        try:
            os.unlink(
                temp_name
            )
        except OSError:
            pass

        raise


def target_value(
    origin_price: float,
    endpoint_price: float,
    elapsed_days: int,
    target: str,
) -> float:

    if (
        origin_price <= 0
        or endpoint_price <= 0
    ):
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

    elif (
        target
        == "ANNUALIZED_RETURN_WHERE_DEFINED"
    ):

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
                / float(
                    elapsed_days
                )
            )
        ) - 1.0

    else:
        raise ValueError(
            f"unknown target {target}"
        )

    if not np.isfinite(
        value
    ):
        raise ValueError(
            "nonfinite target"
        )

    return float(
        value
    )


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

    elif (
        target
        == "ANNUALIZED_RETURN_WHERE_DEFINED"
    ):

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
                    float(
                        horizon
                    )
                    / 365.0
                )
            )
        )

    else:
        raise ValueError(
            f"unknown target {target}"
        )

    if (
        not np.isfinite(
            value
        )
        or value <= 0
    ):
        raise ValueError(
            "invalid predicted price"
        )

    return float(
        value
    )


def feature_vector(
    feature: str,
    canonical_id: str,
    origin_date: date,
    history: dict[
        str,
        list[
            tuple[
                date,
                float,
            ]
        ],
    ],
    release_dates: dict[
        str,
        date,
    ],
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
            "nonpositive origin price"
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

    if (
        feature
        == "PRICE_PLUS_PATH_STABILITY"
    ):

        if len(
            observations
        ) < 2:
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
            len(
                observations
            ),
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
                    float(
                        elapsed
                    )
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
                    )
                    - 1.0
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

        if np.ptp(
            x
        ) <= 0:
            raise ValueError(
                "zero path span"
            )

        slope, _ = np.polyfit(
            x,
            log_prices,
            1,
        )

        values = np.asarray(
            [
                *base,
                volatility,
                max_drawdown,
                float(
                    slope
                ),
            ],
            dtype=float,
        )

        if not np.all(
            np.isfinite(
                values
            )
        ):
            raise ValueError(
                "nonfinite feature"
            )

        return values

    raise ValueError(
        f"unknown feature {feature}"
    )


def estimator_for(
    model: str,
):

    if model == "RANDOM_FOREST":

        return RandomForestRegressor(
            n_estimators=500,
            max_depth=6,
            min_samples_leaf=5,
            max_features=1.0,
            random_state=20260809,
            n_jobs=-1,
        )

    if model == "GRADIENT_BOOSTING":

        return GradientBoostingRegressor(
            n_estimators=250,
            learning_rate=0.03,
            max_depth=2,
            min_samples_leaf=5,
            random_state=20260809,
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

    absolute_error = abs(
        error
    )

    ape = (
        absolute_error
        / actual_price
    )

    denominator = (
        abs(
            predicted_price
        )
        + abs(
            actual_price
        )
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
        np.sign(
            actual_return
        )
        == np.sign(
            predicted_return
        )
    )

    downside_error = max(
        predicted_return
        - actual_return,
        0.0,
    )

    return {
        "error":
            float(
                error
            ),

        "absolute_error":
            float(
                absolute_error
            ),

        "squared_error":
            float(
                error
                * error
            ),

        "ape":
            float(
                ape
            ),

        "smape":
            float(
                smape
            ),

        "actual_return":
            float(
                actual_return
            ),

        "predicted_return":
            float(
                predicted_return
            ),

        "direction_correct":
            direction_correct,

        "downside_error":
            float(
                downside_error
            ),
    }


def safe_rank(
    rows: list[
        dict[
            str,
            object,
        ]
    ],
) -> float | None:

    if len(
        rows
    ) < 2:
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
        len(
            set(
                predicted
            )
        ) < 2
        or len(
            set(
                actual
            )
        ) < 2
    ):
        return None

    value = float(
        spearmanr(
            predicted,
            actual,
        ).statistic
    )

    if not np.isfinite(
        value
    ):
        return None

    return value


def resolve_release_column(
    rows: list[
        dict[
            str,
            str,
        ]
    ],
) -> str:

    for candidate in (
        "release_date",
        "canonical_release_date",
        "resolved_release_date",
        "historical_release_date",
    ):

        if candidate in rows[0]:
            return candidate

    fuzzy = [
        column
        for column in rows[0]
        if (
            "release"
            in column.lower()
            and "date"
            in column.lower()
        )
    ]

    if len(
        fuzzy
    ) != 1:
        fail(
            "unable to resolve release-date column"
        )

    return fuzzy[0]


def checkpoint_name(
    model: str,
    horizon: int,
    origin_date: date,
    feature: str,
    target: str,
) -> str:

    return (
        f"{model}"
        f"__H{horizon}"
        f"__{origin_date.isoformat()}"
        f"__{feature}"
        f"__{target}.json"
    )


def score_rows(
    rows: list[
        dict[
            str,
            object,
        ]
    ],
) -> dict[
    str,
    object,
]:

    if not rows:

        return {
            "prediction_rows": 0,
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

    by_origin = defaultdict(
        list
    )

    for row in rows:

        by_origin[
            clean(
                row[
                    "origin_date"
                ]
            )
        ].append(
            row
        )

    rank_values = []

    for origin_rows in by_origin.values():

        rank = safe_rank(
            origin_rows
        )

        if rank is not None:

            rank_values.append(
                rank
            )

    return {
        "prediction_rows":
            len(
                rows
            ),

        "product_count":
            len(
                {
                    clean(
                        row[
                            "canonical_product_id"
                        ]
                    )
                    for row in rows
                }
            ),

        "origin_count":
            len(
                by_origin
            ),

        "SMAPE":
            float(
                np.mean(
                    [
                        float(
                            row[
                                "smape"
                            ]
                        )
                        for row in rows
                    ]
                )
            ),

        "MAE":
            float(
                np.mean(
                    [
                        float(
                            row[
                                "absolute_error"
                            ]
                        )
                        for row in rows
                    ]
                )
            ),

        "RMSE":
            float(
                math.sqrt(
                    np.mean(
                        [
                            float(
                                row[
                                    "squared_error"
                                ]
                            )
                            for row in rows
                        ]
                    )
                )
            ),

        "MEDIAN_APE":
            float(
                np.median(
                    [
                        float(
                            row[
                                "ape"
                            ]
                        )
                        for row in rows
                    ]
                )
            ),

        "BIAS":
            float(
                np.mean(
                    [
                        float(
                            row[
                                "error"
                            ]
                        )
                        for row in rows
                    ]
                )
            ),

        "DIRECTIONAL_ACCURACY":
            float(
                np.mean(
                    [
                        float(
                            row[
                                "direction_correct"
                            ]
                        )
                        for row in rows
                    ]
                )
            ),

        "DOWNSIDE_ERROR":
            float(
                np.mean(
                    [
                        float(
                            row[
                                "downside_error"
                            ]
                        )
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


def run_tree_batch(
    args,
    canonical_rows,
    history_rows,
    fold_rows_raw,
    matrix_rows,
) -> dict:

    release_column = (
        resolve_release_column(
            canonical_rows
        )
    )

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

    history = defaultdict(
        list
    )

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

    folds_by_horizon = defaultdict(
        list
    )

    validation_groups = defaultdict(
        list
    )

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

        if (
            row[
                "horizon"
            ]
            not in HORIZONS
        ):
            fail(
                "tree fold horizon drift"
            )

        folds_by_horizon[
            row[
                "horizon"
            ]
        ].append(
            row
        )

        validation_groups[
            (
                row[
                    "horizon"
                ],
                row[
                    "origin_date"
                ],
            )
        ].append(
            row
        )

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

        if model not in TREE_MODELS:
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

        cells.append(
            cell
        )

        cell_lookup[
            (
                model,
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

    if len(
        cells
    ) != EXPECTED_TREE_CELLS:

        fail(
            f"tree matrix cells={len(cells)}, "
            f"expected {EXPECTED_TREE_CELLS}"
        )

    feature_cache = {}

    def get_feature(
        feature: str,
        canonical_id: str,
        origin_date_value: date,
    ) -> np.ndarray:

        key = (
            feature,
            canonical_id,
            origin_date_value,
        )

        if key in feature_cache:

            cached = (
                feature_cache[
                    key
                ]
            )

            if isinstance(
                cached,
                Exception,
            ):
                raise cached

            return cached

        try:

            value = feature_vector(
                feature,
                canonical_id,
                origin_date_value,
                history,
                release_dates,
            )

            feature_cache[
                key
            ] = value

            return value

        except Exception as exc:

            stored = ValueError(
                str(
                    exc
                )
            )

            feature_cache[
                key
            ] = stored

            raise stored

    checkpoint_root = (
        args.checkpoint_root.resolve()
    )

    checkpoint_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_groups = (
        len(
            validation_groups
        )
        * len(
            FEATURES
        )
        * len(
            TARGETS
        )
        * len(
            TREE_MODELS
        )
    )

    completed_existing = len(
        list(
            checkpoint_root.glob(
                "*.json"
            )
        )
    )

    print(
        "TREE_CHECKPOINT_DIRECTORY="
        f"{checkpoint_root}",
        flush=True,
    )

    print(
        "TREE_TOTAL_GROUPS="
        f"{total_groups}",
        flush=True,
    )

    print(
        "TREE_EXISTING_CHECKPOINTS="
        f"{completed_existing}",
        flush=True,
    )

    processed_counter = 0

    for model in TREE_MODELS:

        print(
            f"START_TREE_MODEL={model}",
            flush=True,
        )

        model_groups = 0
        model_reused = 0
        model_new = 0

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

                for target in TARGETS:

                    model_groups += 1
                    processed_counter += 1

                    group_id = (
                        checkpoint_name(
                            model,
                            horizon,
                            validation_origin,
                            feature,
                            target,
                        )
                    )

                    checkpoint_path = (
                        checkpoint_root
                        / group_id
                    )

                    if checkpoint_path.is_file():

                        try:

                            existing = json.loads(
                                checkpoint_path.read_text(
                                    encoding="utf-8"
                                )
                            )

                        except Exception as exc:

                            fail(
                                "corrupt tree checkpoint "
                                f"{checkpoint_path.name}: "
                                f"{exc}"
                            )

                        if (
                            existing.get(
                                "group_id"
                            )
                            != group_id
                        ):
                            fail(
                                "tree checkpoint identity drift"
                            )

                        model_reused += 1

                        if (
                            processed_counter % 25
                            == 0
                        ):
                            print(
                                (
                                    "TREE_PROGRESS="
                                    f"{processed_counter}/{total_groups}"
                                    f"|MODEL={model}"
                                    f"|REUSED={model_reused}"
                                    f"|NEW={model_new}"
                                ),
                                flush=True,
                            )

                        continue

                    combination_id = (
                        cell_lookup[
                            (
                                model,
                                feature,
                                target,
                                horizon,
                            )
                        ]
                    )

                    training_x = []
                    training_y = []

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

                        training_x.append(
                            x
                        )

                        training_y.append(
                            y
                        )

                    payload = {
                        "group_id":
                            group_id,

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

                        "combination_id":
                            combination_id,

                        "training_rows":
                            len(
                                training_x
                            ),

                        "fit_status":
                            "",

                        "predictions":
                            [],

                        "skips":
                            [],
                    }

                    if (
                        len(
                            training_x
                        )
                        < MIN_TRAINING_ROWS
                    ):

                        payload[
                            "fit_status"
                        ] = (
                            "SKIPPED_INSUFFICIENT_TRAINING_ROWS"
                        )

                        for fold in validation_folds:

                            payload[
                                "skips"
                            ].append(
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
                                            "INSUFFICIENT_MATURED_"
                                            "TRAINING_ROWS:"
                                            f"{len(training_x)}"
                                        ),
                                }
                            )

                        atomic_json_write(
                            checkpoint_path,
                            payload,
                        )

                        model_new += 1

                    else:

                        X_train = np.vstack(
                            training_x
                        )

                        y_train = np.asarray(
                            training_y,
                            dtype=float,
                        )

                        estimator = (
                            estimator_for(
                                model
                            )
                        )

                        try:

                            estimator.fit(
                                X_train,
                                y_train,
                            )

                        except Exception as exc:

                            payload[
                                "fit_status"
                            ] = "FIT_FAILURE"

                            for fold in validation_folds:

                                payload[
                                    "skips"
                                ].append(
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
                                                + str(
                                                    exc
                                                )
                                            ),
                                    }
                                )

                            atomic_json_write(
                                checkpoint_path,
                                payload,
                            )

                            model_new += 1

                        else:

                            payload[
                                "fit_status"
                            ] = "FIT_SUCCESS"

                            for fold in validation_folds:

                                try:

                                    x_val = get_feature(
                                        feature,
                                        fold[
                                            "canonical_product_id"
                                        ],
                                        fold[
                                            "origin_date"
                                        ],
                                    )

                                    predicted_target = float(
                                        estimator.predict(
                                            x_val.reshape(
                                                1,
                                                -1,
                                            )
                                        )[0]
                                    )

                                    predicted_price = (
                                        invert_target(
                                            fold[
                                                "origin_price"
                                            ],
                                            predicted_target,
                                            horizon,
                                            target,
                                        )
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

                                    payload[
                                        "skips"
                                    ].append(
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
                                                    "PREDICTION_FAILURE:"
                                                    + str(
                                                        exc
                                                    )
                                                ),
                                        }
                                    )

                                    continue

                                payload[
                                    "predictions"
                                ].append(
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

                                        **metrics,
                                    }
                                )

                            atomic_json_write(
                                checkpoint_path,
                                payload,
                            )

                            model_new += 1

                    if (
                        processed_counter % 10
                        == 0
                    ):

                        print(
                            (
                                "TREE_PROGRESS="
                                f"{processed_counter}/{total_groups}"
                                f"|MODEL={model}"
                                f"|H={horizon}"
                                f"|FEATURE={feature}"
                                f"|TARGET={target}"
                                f"|REUSED={model_reused}"
                                f"|NEW={model_new}"
                            ),
                            flush=True,
                        )

        print(
            (
                f"COMPLETE_TREE_MODEL={model}"
                f"|GROUPS={model_groups}"
                f"|REUSED={model_reused}"
                f"|NEW={model_new}"
            ),
            flush=True,
        )

    checkpoints = sorted(
        checkpoint_root.glob(
            "*.json"
        )
    )

    if len(
        checkpoints
    ) != total_groups:

        fail(
            "tree checkpoint completion mismatch: "
            f"{len(checkpoints)}/{total_groups}"
        )

    predictions = []
    skips = []
    fit_rows = []

    for checkpoint_path in checkpoints:

        payload = json.loads(
            checkpoint_path.read_text(
                encoding="utf-8"
            )
        )

        predictions.extend(
            payload.get(
                "predictions",
                [],
            )
        )

        skips.extend(
            payload.get(
                "skips",
                [],
            )
        )

        fit_rows.append(
            {
                "group_id":
                    payload[
                        "group_id"
                    ],

                "model_family":
                    payload[
                        "model_family"
                    ],

                "feature_variant":
                    payload[
                        "feature_variant"
                    ],

                "target_transformation":
                    payload[
                        "target_transformation"
                    ],

                "requested_horizon_days":
                    payload[
                        "requested_horizon_days"
                    ],

                "validation_origin":
                    payload[
                        "validation_origin"
                    ],

                "training_rows":
                    payload[
                        "training_rows"
                    ],

                "fit_status":
                    payload[
                        "fit_status"
                    ],
            }
        )

    prediction_groups = defaultdict(
        list
    )

    skip_counts = defaultdict(
        int
    )

    for row in predictions:

        prediction_groups[
            clean(
                row[
                    "combination_id"
                ]
            )
        ].append(
            row
        )

    for row in skips:

        skip_counts[
            clean(
                row[
                    "combination_id"
                ]
            )
        ] += 1

    cell_scorecard = []

    for cell in cells:

        combination_id = (
            cell[
                "combination_id"
            ]
        )

        rows = prediction_groups.get(
            combination_id,
            [],
        )

        metrics = score_rows(
            rows
        )

        cell_scorecard.append(
            {
                **cell,
                **metrics,
                "skipped_rows":
                    skip_counts[
                        combination_id
                    ],
            }
        )

    if len(
        cell_scorecard
    ) != EXPECTED_TREE_CELLS:

        fail(
            "tree cell scorecard count drift"
        )

    product_groups = defaultdict(
        list
    )

    for row in predictions:

        product_groups[
            (
                clean(
                    row[
                        "combination_id"
                    ]
                ),
                clean(
                    row[
                        "canonical_product_id"
                    ]
                ),
                clean(
                    row[
                        "product_name"
                    ]
                ),
            )
        ].append(
            row
        )

    product_rows = []

    for (
        combination_id,
        canonical_id,
        product_name,
    ), rows in sorted(
        product_groups.items()
    ):

        metrics = score_rows(
            rows
        )

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
                    metrics[
                        "prediction_rows"
                    ],

                "SMAPE":
                    metrics[
                        "SMAPE"
                    ],

                "MAE":
                    metrics[
                        "MAE"
                    ],

                "BIAS":
                    metrics[
                        "BIAS"
                    ],
            }
        )

    tree_output_root = (
        args.tree_output_root.resolve()
    )

    tree_output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    prediction_path = (
        tree_output_root
        / "precollector_15wd_prediction_ledger_v1.csv"
    )

    cell_path = (
        tree_output_root
        / "precollector_15wd_cell_scorecard_v1.csv"
    )

    fit_path = (
        tree_output_root
        / "precollector_15wd_fit_ledger_v1.csv"
    )

    product_path = (
        tree_output_root
        / "precollector_15wd_product_oos_error_ledger_v1.csv"
    )

    skipped_path = (
        tree_output_root
        / "precollector_15wd_skipped_fold_ledger_v1.csv"
    )

    summary_path = (
        tree_output_root
        / "precollector_15wd_summary_v1.json"
    )

    manifest_path = (
        tree_output_root
        / "precollector_15wd_manifest_v1.json"
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
        cell_path,
        cell_scorecard,
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
        fit_rows,
        [
            "group_id",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "validation_origin",
            "training_rows",
            "fit_status",
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
        skips,
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
        for row in fit_rows
        if (
            row[
                "fit_status"
            ]
            == "FIT_SUCCESS"
        )
    )

    failed_fits = sum(
        1
        for row in fit_rows
        if (
            row[
                "fit_status"
            ]
            == "FIT_FAILURE"
        )
    )

    insufficient_groups = sum(
        1
        for row in fit_rows
        if (
            row[
                "fit_status"
            ]
            == "SKIPPED_INSUFFICIENT_TRAINING_ROWS"
        )
    )

    descriptive = {}

    for horizon in HORIZONS:

        candidates = [
            row
            for row in cell_scorecard
            if (
                int(
                    row[
                        "requested_horizon_days"
                    ]
                )
                == horizon
                and row[
                    "SMAPE"
                ]
                != ""
            )
        ]

        if candidates:

            best = min(
                candidates,
                key=lambda row: float(
                    row[
                        "SMAPE"
                    ]
                ),
            )

            descriptive[
                str(
                    horizon
                )
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
                    float(
                        best[
                            "SMAPE"
                        ]
                    ),

                "status":
                    "DESCRIPTIVE_TREE_BATCH_NOT_CERTIFIED_WINNER",
            }

    summary = {
        "status":
            "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_D",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "models_executed":
            list(
                TREE_MODELS
            ),

        "model_count":
            2,

        "governed_matrix_cells":
            len(
                cell_scorecard
            ),

        "checkpoint_groups":
            len(
                checkpoints
            ),

        "prediction_rows":
            len(
                predictions
            ),

        "skipped_rows":
            len(
                skips
            ),

        "successful_fits":
            successful_fits,

        "fit_failures":
            failed_fits,

        "insufficient_training_fit_groups":
            insufficient_groups,

        "descriptive_lowest_smape":
            descriptive,

        "certified_winner_selected":
            False,

        "product_exclusions_assigned":
            0,

        "production_model_selection_authorized":
            False,

        "monte_carlo_execution_authorized":
            False,
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
        cell_path,
        fit_path,
        product_path,
        skipped_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_15wd_manifest_v1",

        "runner_sha256_pre_execution":
            args.runner_sha256,

        "contract_sha256_pre_execution":
            args.contract_sha256,

        "members": [
            {
                "file_name":
                    member.name,

                "sha256":
                    sha256_file(
                        member
                    ),

                "byte_length":
                    member.stat().st_size,
            }
            for member in members
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
        "PASS_PRECOLLECTOR_BASE_TEMPORAL_OOS_BATCH_15W_D",
        flush=True,
    )

    print(
        f"TREE_CHECKPOINT_GROUPS={len(checkpoints)}",
        flush=True,
    )

    print(
        f"TREE_PREDICTION_ROWS={len(predictions)}",
        flush=True,
    )

    print(
        f"TREE_SKIPPED_ROWS={len(skips)}",
        flush=True,
    )

    print(
        f"TREE_SUCCESSFUL_FITS={successful_fits}",
        flush=True,
    )

    print(
        f"TREE_FIT_FAILURES={failed_fits}",
        flush=True,
    )

    for horizon in HORIZONS:

        best = descriptive.get(
            str(
                horizon
            )
        )

        if best:

            print(
                (
                    f"HORIZON_{horizon}_LOWEST_TREE_SMAPE="
                    f"{best['combination_id']}|"
                    f"{best['model_family']}|"
                    f"{best['feature_variant']}|"
                    f"{best['target_transformation']}|"
                    f"{best['SMAPE']:.8f}"
                ),
                flush=True,
            )

    return {
        "prediction_path":
            prediction_path,

        "cell_path":
            cell_path,

        "summary_path":
            summary_path,

        "summary":
            summary,
    }


def normalize_prediction_row(
    row: dict[str, str],
    source_batch: str,
) -> dict[str, object]:

    result = {
        key:
            value
        for key, value in row.items()
    }

    result[
        "source_batch"
    ] = source_batch

    result[
        "model_family"
    ] = clean(
        row[
            "model_family"
        ]
    )

    result[
        "semantic_model_key"
    ] = clean(
        row[
            "semantic_model_key"
        ]
    )

    result[
        "fold_id"
    ] = clean(
        row[
            "fold_id"
        ]
    )

    result[
        "canonical_product_id"
    ] = clean(
        row[
            "canonical_product_id"
        ]
    )

    result[
        "origin_date"
    ] = clean(
        row[
            "origin_date"
        ]
    )

    result[
        "requested_horizon_days"
    ] = int(
        row[
            "requested_horizon_days"
        ]
    )

    for column in (
        "origin_price",
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
    ):

        result[
            column
        ] = float(
            row[
                column
            ]
        )

    return result


def reconcile(
    args,
    tree_result,
) -> dict:

    a_predictions_raw = read_zip_csv(
        args.batch_a_package,
        "precollector_15wa_semantic_prediction_ledger_v1.csv",
    )

    b_predictions_raw = read_zip_csv(
        args.batch_b_package,
        "precollector_15wb_prediction_ledger_v1.csv",
    )

    c_predictions_raw = read_zip_csv(
        args.batch_c_package,
        "precollector_15wc_prediction_ledger_v1.csv",
    )

    with tree_result[
        "prediction_path"
    ].open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        d_predictions_raw = list(
            csv.DictReader(
                handle
            )
        )

    a_cells = read_zip_csv(
        args.batch_a_package,
        "precollector_15wa_governed_cell_scorecard_v1.csv",
    )

    b_cells = read_zip_csv(
        args.batch_b_package,
        "precollector_15wb_cell_scorecard_v1.csv",
    )

    c_cells = read_zip_csv(
        args.batch_c_package,
        "precollector_15wc_cell_scorecard_v1.csv",
    )

    with tree_result[
        "cell_path"
    ].open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        d_cells = list(
            csv.DictReader(
                handle
            )
        )

    full_cells = (
        [
            {
                **row,
                "source_batch":
                    "15W-A",
            }
            for row in a_cells
        ]
        + [
            {
                **row,
                "source_batch":
                    "15W-B",
            }
            for row in b_cells
        ]
        + [
            {
                **row,
                "source_batch":
                    "15W-C",
            }
            for row in c_cells
        ]
        + [
            {
                **row,
                "source_batch":
                    "15W-D",
            }
            for row in d_cells
        ]
    )

    if len(
        full_cells
    ) != EXPECTED_BASE_CELLS:

        fail(
            "base 396-cell reconciliation failed: "
            f"got {len(full_cells)}"
        )

    normalized = []

    for source_batch, rows in (
        (
            "15W-A",
            a_predictions_raw,
        ),
        (
            "15W-B",
            b_predictions_raw,
        ),
        (
            "15W-C",
            c_predictions_raw,
        ),
        (
            "15W-D",
            d_predictions_raw,
        ),
    ):

        for row in rows:

            normalized.append(
                normalize_prediction_row(
                    row,
                    source_batch,
                )
            )

    # ========================================================================
    # Semantic deduplication
    #
    # 15W-A repeats no semantic rows.
    # 15W-C median may repeat identical predictions across feature cells.
    # Any duplicate semantic key + fold MUST have identical predictions.
    # ========================================================================

    deduped = {}

    duplicate_rows = 0

    for row in normalized:

        key = (
            row[
                "semantic_model_key"
            ],
            row[
                "fold_id"
            ],
        )

        if key in deduped:

            existing = deduped[
                key
            ]

            if not math.isclose(
                float(
                    existing[
                        "predicted_endpoint_price"
                    ]
                ),
                float(
                    row[
                        "predicted_endpoint_price"
                    ]
                ),
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                fail(
                    "semantic duplicate prediction mismatch "
                    f"for {key}"
                )

            duplicate_rows += 1
            continue

        deduped[
            key
        ] = row

    semantic_predictions = list(
        deduped.values()
    )

    semantic_groups = defaultdict(
        list
    )

    for row in semantic_predictions:

        semantic_groups[
            (
                row[
                    "requested_horizon_days"
                ],
                row[
                    "semantic_model_key"
                ],
            )
        ].append(
            row
        )

    raw_scorecard = []

    for (
        horizon,
        semantic_key,
    ), rows in sorted(
        semantic_groups.items()
    ):

        metrics = score_rows(
            rows
        )

        raw_scorecard.append(
            {
                "requested_horizon_days":
                    horizon,

                "semantic_model_key":
                    semantic_key,

                "model_family":
                    rows[0][
                        "model_family"
                    ],

                "source_batch":
                    rows[0][
                        "source_batch"
                    ],

                **metrics,
            }
        )

    # ========================================================================
    # COMMON-FOLD PAIRED COMPARISON
    # ========================================================================

    common_fold_rows = []

    paired_scorecard = []

    common_fold_counts = {}

    for horizon in HORIZONS:

        horizon_groups = {
            semantic_key:
                rows
            for (
                group_horizon,
                semantic_key,
            ), rows in semantic_groups.items()
            if group_horizon == horizon
        }

        if not horizon_groups:

            fail(
                f"no semantic models for horizon {horizon}"
            )

        fold_sets = [
            {
                row[
                    "fold_id"
                ]
                for row in rows
            }
            for rows in horizon_groups.values()
        ]

        common_folds = set.intersection(
            *fold_sets
        )

        if not common_folds:

            fail(
                f"common-fold intersection empty "
                f"for horizon {horizon}"
            )

        common_fold_counts[
            str(
                horizon
            )
        ] = len(
            common_folds
        )

        for semantic_key, rows in sorted(
            horizon_groups.items()
        ):

            selected = [
                row
                for row in rows
                if (
                    row[
                        "fold_id"
                    ]
                    in common_folds
                )
            ]

            if len(
                selected
            ) != len(
                common_folds
            ):

                fail(
                    "paired comparison row count drift"
                )

            metrics = score_rows(
                selected
            )

            paired_scorecard.append(
                {
                    "requested_horizon_days":
                        horizon,

                    "semantic_model_key":
                        semantic_key,

                    "model_family":
                        selected[0][
                            "model_family"
                        ],

                    "source_batch":
                        selected[0][
                            "source_batch"
                        ],

                    "common_fold_count":
                        len(
                            common_folds
                        ),

                    **metrics,
                }
            )

            for row in selected:

                common_fold_rows.append(
                    {
                        "requested_horizon_days":
                            horizon,

                        "semantic_model_key":
                            semantic_key,

                        "model_family":
                            row[
                                "model_family"
                            ],

                        "source_batch":
                            row[
                                "source_batch"
                            ],

                        "fold_id":
                            row[
                                "fold_id"
                            ],

                        "canonical_product_id":
                            row[
                                "canonical_product_id"
                            ],

                        "origin_date":
                            row[
                                "origin_date"
                            ],

                        "predicted_endpoint_price":
                            row[
                                "predicted_endpoint_price"
                            ],

                        "actual_endpoint_price":
                            row[
                                "actual_endpoint_price"
                            ],

                        "smape":
                            row[
                                "smape"
                            ],

                        "absolute_error":
                            row[
                                "absolute_error"
                            ],

                        "actual_return":
                            row[
                                "actual_return"
                            ],

                        "predicted_return":
                            row[
                                "predicted_return"
                            ],
                    }
                )

    # ========================================================================
    # DESCRIPTIVE HORIZON RANKING — paired common-fold only
    # ========================================================================

    horizon_ranking = []

    descriptive_best = {}

    for horizon in HORIZONS:

        candidates = [
            row
            for row in paired_scorecard
            if (
                int(
                    row[
                        "requested_horizon_days"
                    ]
                )
                == horizon
            )
        ]

        candidates.sort(
            key=lambda row: (
                float(
                    row[
                        "SMAPE"
                    ]
                ),
                float(
                    row[
                        "MAE"
                    ]
                ),
            )
        )

        for rank, row in enumerate(
            candidates,
            start=1,
        ):

            horizon_ranking.append(
                {
                    "requested_horizon_days":
                        horizon,

                    "descriptive_rank":
                        rank,

                    "semantic_model_key":
                        row[
                            "semantic_model_key"
                        ],

                    "model_family":
                        row[
                            "model_family"
                        ],

                    "source_batch":
                        row[
                            "source_batch"
                        ],

                    "common_fold_count":
                        row[
                            "common_fold_count"
                        ],

                    "SMAPE":
                        row[
                            "SMAPE"
                        ],

                    "MAE":
                        row[
                            "MAE"
                        ],

                    "RMSE":
                        row[
                            "RMSE"
                        ],

                    "BIAS":
                        row[
                            "BIAS"
                        ],

                    "DIRECTIONAL_ACCURACY":
                        row[
                            "DIRECTIONAL_ACCURACY"
                        ],

                    "DOWNSIDE_ERROR":
                        row[
                            "DOWNSIDE_ERROR"
                        ],

                    "status":
                        "DESCRIPTIVE_BASE_RANK_NOT_CERTIFIED_WINNER",
                }
            )

        best = candidates[0]

        descriptive_best[
            str(
                horizon
            )
        ] = {
            "semantic_model_key":
                best[
                    "semantic_model_key"
                ],

            "model_family":
                best[
                    "model_family"
                ],

            "source_batch":
                best[
                    "source_batch"
                ],

            "common_fold_count":
                best[
                    "common_fold_count"
                ],

            "SMAPE":
                best[
                    "SMAPE"
                ],

            "MAE":
                best[
                    "MAE"
                ],

            "status":
                "DESCRIPTIVE_PAIRED_BASE_RESULT_NOT_CERTIFIED_WINNER",
        }

    # ========================================================================
    # COVERAGE
    # ========================================================================

    coverage_rows = []

    total_fold_count_by_horizon = defaultdict(
        set
    )

    for row in semantic_predictions:

        total_fold_count_by_horizon[
            row[
                "requested_horizon_days"
            ]
        ].add(
            row[
                "fold_id"
            ]
        )

    for row in raw_scorecard:

        horizon = int(
            row[
                "requested_horizon_days"
            ]
        )

        total_horizon_folds = len(
            total_fold_count_by_horizon[
                horizon
            ]
        )

        coverage_rows.append(
            {
                "requested_horizon_days":
                    horizon,

                "semantic_model_key":
                    row[
                        "semantic_model_key"
                    ],

                "model_family":
                    row[
                        "model_family"
                    ],

                "source_batch":
                    row[
                        "source_batch"
                    ],

                "prediction_rows":
                    row[
                        "prediction_rows"
                    ],

                "observed_horizon_fold_universe":
                    total_horizon_folds,

                "coverage_fraction":
                    (
                        float(
                            row[
                                "prediction_rows"
                            ]
                        )
                        / float(
                            total_horizon_folds
                        )
                    ),

                "common_fold_count":
                    common_fold_counts[
                        str(
                            horizon
                        )
                    ],
            }
        )

    output_root = (
        args.reconciliation_output_root.resolve()
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    full_cell_path = (
        output_root
        / "precollector_base_396_cell_scorecard_v1.csv"
    )

    raw_path = (
        output_root
        / "precollector_base_semantic_raw_scorecard_v1.csv"
    )

    paired_path = (
        output_root
        / "precollector_base_common_fold_paired_scorecard_v1.csv"
    )

    ranking_path = (
        output_root
        / "precollector_base_common_fold_descriptive_ranking_v1.csv"
    )

    coverage_path = (
        output_root
        / "precollector_base_semantic_coverage_ledger_v1.csv"
    )

    common_prediction_path = (
        output_root
        / "precollector_base_common_fold_prediction_ledger_v1.csv"
    )

    summary_path = (
        output_root
        / "precollector_base_tournament_reconciliation_summary_v1.json"
    )

    manifest_path = (
        output_root
        / "precollector_base_tournament_reconciliation_manifest_v1.json"
    )

    all_cell_fields = sorted(
        {
            key
            for row in full_cells
            for key in row.keys()
        }
    )

    write_csv(
        full_cell_path,
        full_cells,
        all_cell_fields,
    )

    write_csv(
        raw_path,
        raw_scorecard,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "source_batch",
            "prediction_rows",
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
        paired_path,
        paired_scorecard,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "source_batch",
            "common_fold_count",
            "prediction_rows",
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
        ranking_path,
        horizon_ranking,
        [
            "requested_horizon_days",
            "descriptive_rank",
            "semantic_model_key",
            "model_family",
            "source_batch",
            "common_fold_count",
            "SMAPE",
            "MAE",
            "RMSE",
            "BIAS",
            "DIRECTIONAL_ACCURACY",
            "DOWNSIDE_ERROR",
            "status",
        ],
    )

    write_csv(
        coverage_path,
        coverage_rows,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "source_batch",
            "prediction_rows",
            "observed_horizon_fold_universe",
            "coverage_fraction",
            "common_fold_count",
        ],
    )

    write_csv(
        common_prediction_path,
        common_fold_rows,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "source_batch",
            "fold_id",
            "canonical_product_id",
            "origin_date",
            "predicted_endpoint_price",
            "actual_endpoint_price",
            "smape",
            "absolute_error",
            "actual_return",
            "predicted_return",
        ],
    )

    semantic_model_counts = {
        str(
            horizon
        ):
        len(
            {
                row[
                    "semantic_model_key"
                ]
                for row in paired_scorecard
                if (
                    int(
                        row[
                            "requested_horizon_days"
                        ]
                    )
                    == horizon
                )
            }
        )
        for horizon in HORIZONS
    }

    summary = {
        "status":
            "PASS_PRECOLLECTOR_COMPLETE_BASE_TEMPORAL_OOS_TOURNAMENT_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "governed_base_cells":
            len(
                full_cells
            ),

        "base_model_families":
            11,

        "source_batches":
            [
                "15W-A",
                "15W-B",
                "15W-C",
                "15W-D",
            ],

        "normalized_prediction_rows_before_semantic_deduplication":
            len(
                normalized
            ),

        "semantic_duplicate_rows_removed":
            duplicate_rows,

        "semantic_unique_prediction_rows":
            len(
                semantic_predictions
            ),

        "semantic_model_counts_by_horizon":
            semantic_model_counts,

        "common_fold_counts_by_horizon":
            common_fold_counts,

        "paired_common_fold_comparison_completed":
            True,

        "descriptive_best_paired_base_models":
            descriptive_best,

        "descriptive_best_is_certified_winner":
            False,

        "product_holdout_executed":
            False,

        "statistical_influence_executed":
            False,

        "exclusion_sensitivity_executed":
            False,

        "product_treatments_assigned":
            0,

        "product_exclusions_assigned":
            0,

        "ensemble_execution_authorized":
            False,

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

        "authorized_next_large_step":
            "RUN_PRECOLLECTOR_ENSEMBLES_AND_ROBUSTNESS_DIAGNOSTICS",
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
        full_cell_path,
        raw_path,
        paired_path,
        ranking_path,
        coverage_path,
        common_prediction_path,
        summary_path,
    ]

    manifest = {
        "manifest_id":
            "precollector_complete_base_temporal_oos_tournament_v1",

        "input_package_sha256": {
            "batch_15w_a":
                sha256_file(
                    args.batch_a_package
                ),

            "batch_15w_b":
                sha256_file(
                    args.batch_b_package
                ),

            "batch_15w_c":
                sha256_file(
                    args.batch_c_package
                ),
        },

        "tree_outputs": {
            "prediction_ledger_sha256":
                sha256_file(
                    tree_result[
                        "prediction_path"
                    ]
                ),

            "cell_scorecard_sha256":
                sha256_file(
                    tree_result[
                        "cell_path"
                    ]
                ),
        },

        "members": [
            {
                "file_name":
                    path.name,

                "sha256":
                    sha256_file(
                        path
                    ),

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
        "PASS_PRECOLLECTOR_COMPLETE_BASE_TEMPORAL_OOS_TOURNAMENT_V1",
        flush=True,
    )

    print(
        "BASE_MODEL_FAMILIES=11",
        flush=True,
    )

    print(
        f"GOVERNED_BASE_CELLS={len(full_cells)}",
        flush=True,
    )

    print(
        "PAIRED_COMMON_FOLD_COMPARISON_COMPLETED=TRUE",
        flush=True,
    )

    for horizon in HORIZONS:

        best = descriptive_best[
            str(
                horizon
            )
        ]

        print(
            (
                f"HORIZON_{horizon}_PAIRED_BASE_DESCRIPTIVE_BEST="
                f"{best['semantic_model_key']}|"
                f"SMAPE={float(best['SMAPE']):.8f}|"
                f"MAE={float(best['MAE']):.8f}|"
                f"COMMON_FOLDS={best['common_fold_count']}"
            ),
            flush=True,
        )

    print(
        "DESCRIPTIVE_BEST_IS_CERTIFIED_WINNER=FALSE",
        flush=True,
    )

    print(
        "PRODUCT_HOLDOUT_EXECUTED=FALSE",
        flush=True,
    )

    print(
        "PRODUCT_EXCLUSIONS_ASSIGNED=0",
        flush=True,
    )

    return {
        "summary":
            summary,

        "summary_path":
            summary_path,

        "manifest_path":
            manifest_path,
    }


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
        "--batch-a-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--batch-b-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--batch-c-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--checkpoint-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--tree-output-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--reconciliation-output-root",
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

    if len(
        canonical_rows
    ) != 131:
        fail(
            "canonical count drift"
        )

    if len(
        history_rows
    ) != 3390:
        fail(
            "history count drift"
        )

    if len(
        fold_rows_raw
    ) != 7803:
        fail(
            "fold ledger count drift"
        )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "PHASE_A_CHECKPOINTED_TREE_EXECUTION",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    tree_result = run_tree_batch(
        args,
        canonical_rows,
        history_rows,
        fold_rows_raw,
        matrix_rows,
    )

    print(
        "",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "PHASE_B_COMPLETE_BASE_RECONCILIATION",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    reconciliation = reconcile(
        args,
        tree_result,
    )

    print(
        "",
        flush=True,
    )

    print(
        "FINISH_BASE_TOURNAMENT_PASS",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )