from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
import zipfile

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from sklearn.linear_model import (
    HuberRegressor,
    Ridge,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


HORIZONS = (90, 180, 365)

ROUTES = {
    "TIME_SERIES": {
        "LAST_VALUE",
        "DRIFT",
        "LOG_DRIFT",
        "ROBUST_TREND",
        "EXPONENTIAL_SMOOTHING",
    },
    "POOLED": {
        "RIDGE_REGRESSION",
        "HUBER_REGRESSION",
    },
    "PEER": {
        "PEER_MEDIAN_RETURN",
        "PEER_WEIGHTED_RETURN",
    },
    "TREE": {
        "RANDOM_FOREST",
        "GRADIENT_BOOSTING",
    },
}

EPSILON = 1e-9
MIN_SUPERVISED_ROWS = 20


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


def read_zip_json(
    package: Path,
    member: str,
) -> dict:

    with zipfile.ZipFile(
        package,
        "r",
    ) as archive:

        if member not in archive.namelist():
            fail(
                f"missing ZIP JSON member {member}"
            )

        raw = archive.read(
            member
        ).decode(
            "utf-8-sig"
        )

    return json.loads(raw)


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


def atomic_json(
    path: Path,
    payload: dict,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="lopo_",
        suffix=".tmp",
        dir=str(path.parent),
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
            os.unlink(temp_name)
        except OSError:
            pass

        raise


def mean(values):
    return float(
        np.mean(
            np.asarray(
                values,
                dtype=float,
            )
        )
    )


def std(values):
    if not values:
        return 0.0

    return float(
        np.std(
            np.asarray(
                values,
                dtype=float,
            ),
            ddof=0,
        )
    )


def model_route(family: str) -> str:

    for route, families in ROUTES.items():
        if family in families:
            return route

    fail(
        f"unknown route for model family {family}"
    )


def reconstruct_origin_price(
    actual_endpoint_price: float,
    actual_return: float,
) -> float:

    denominator = (
        1.0
        + actual_return
    )

    if denominator <= 0:
        fail(
            "unable to reconstruct origin price"
        )

    return float(
        actual_endpoint_price
        / denominator
    )


def metrics(
    origin_price: float,
    actual: float,
    predicted: float,
) -> dict[str, float]:

    error = (
        predicted
        - actual
    )

    absolute_error = abs(error)

    denominator = (
        abs(predicted)
        + abs(actual)
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
        actual
        / origin_price
    ) - 1.0

    predicted_return = (
        predicted
        / origin_price
    ) - 1.0

    return {
        "error":
            float(error),

        "absolute_error":
            float(absolute_error),

        "squared_error":
            float(error * error),

        "smape":
            float(smape),

        "actual_return":
            float(actual_return),

        "predicted_return":
            float(predicted_return),

        "direction_correct":
            float(
                np.sign(actual_return)
                == np.sign(predicted_return)
            ),

        "downside_error":
            float(
                max(
                    predicted_return
                    - actual_return,
                    0.0,
                )
            ),
    }


def score(rows):

    if not rows:
        return {
            "prediction_rows": 0,
            "SMAPE": "",
            "MAE": "",
            "RMSE": "",
            "BIAS": "",
            "DIRECTIONAL_ACCURACY": "",
            "DOWNSIDE_ERROR": "",
        }

    return {
        "prediction_rows":
            len(rows),

        "SMAPE":
            mean(
                [
                    row["smape"]
                    for row in rows
                ]
            ),

        "MAE":
            mean(
                [
                    row["absolute_error"]
                    for row in rows
                ]
            ),

        "RMSE":
            float(
                math.sqrt(
                    mean(
                        [
                            row["squared_error"]
                            for row in rows
                        ]
                    )
                )
            ),

        "BIAS":
            mean(
                [
                    row["error"]
                    for row in rows
                ]
            ),

        "DIRECTIONAL_ACCURACY":
            mean(
                [
                    row["direction_correct"]
                    for row in rows
                ]
            ),

        "DOWNSIDE_ERROR":
            mean(
                [
                    row["downside_error"]
                    for row in rows
                ]
            ),
    }


def normalize_base_row(row):

    actual = float(
        row[
            "actual_endpoint_price"
        ]
    )

    actual_return = float(
        row[
            "actual_return"
        ]
    )

    origin_price = (
        reconstruct_origin_price(
            actual,
            actual_return,
        )
    )

    predicted = float(
        row[
            "predicted_endpoint_price"
        ]
    )

    row_metrics = metrics(
        origin_price,
        actual,
        predicted,
    )

    return {
        "requested_horizon_days":
            int(
                row[
                    "requested_horizon_days"
                ]
            ),

        "semantic_model_key":
            clean(
                row[
                    "semantic_model_key"
                ]
            ),

        "model_family":
            clean(
                row[
                    "model_family"
                ]
            ),

        "source_batch":
            clean(
                row[
                    "source_batch"
                ]
            ),

        "fold_id":
            clean(
                row[
                    "fold_id"
                ]
            ),

        "canonical_product_id":
            clean(
                row[
                    "canonical_product_id"
                ]
            ),

        "origin_date":
            clean(
                row[
                    "origin_date"
                ]
            ),

        "origin_price":
            origin_price,

        "actual_endpoint_price":
            actual,

        "predicted_endpoint_price":
            predicted,

        **row_metrics,
    }


def nested_ensembles(base_rows):

    output = []
    selection = []

    for horizon in HORIZONS:

        horizon_rows = [
            row
            for row in base_rows
            if (
                row[
                    "requested_horizon_days"
                ]
                == horizon
            )
        ]

        origins = sorted(
            {
                parse_date(
                    row[
                        "origin_date"
                    ]
                )
                for row in horizon_rows
            }
        )

        for current_origin in origins:

            prior = [
                row
                for row in horizon_rows
                if (
                    parse_date(
                        row[
                            "origin_date"
                        ]
                    )
                    < current_origin
                )
            ]

            current = [
                row
                for row in horizon_rows
                if (
                    parse_date(
                        row[
                            "origin_date"
                        ]
                    )
                    == current_origin
                )
            ]

            if not prior:
                continue

            prior_by_model = defaultdict(list)

            for row in prior:
                prior_by_model[
                    row[
                        "semantic_model_key"
                    ]
                ].append(row)

            prior_smape = {
                key:
                    mean(
                        [
                            row["smape"]
                            for row in rows
                        ]
                    )
                for key, rows
                in prior_by_model.items()
            }

            current_by_fold = defaultdict(dict)

            for row in current:

                current_by_fold[
                    row[
                        "fold_id"
                    ]
                ][
                    row[
                        "semantic_model_key"
                    ]
                ] = row

            route_candidates = defaultdict(list)

            family_candidates = defaultdict(list)

            for key in prior_smape:

                family = key.split("|")[0]

                route_candidates[
                    model_route(family)
                ].append(key)

                family_candidates[
                    family
                ].append(key)

            route_champions = [
                min(
                    keys,
                    key=lambda key:
                        prior_smape[key],
                )
                for keys
                in route_candidates.values()
            ]

            family_champions = [
                min(
                    keys,
                    key=lambda key:
                        prior_smape[key],
                )
                for keys
                in family_candidates.values()
            ]

            definitions = {
                "ROUTE_ENSEMBLE":
                    route_champions,

                "GLOBAL_ENSEMBLE":
                    family_champions,
            }

            for ensemble_family, components in (
                definitions.items()
            ):

                if len(components) < 2:
                    continue

                selection.append(
                    {
                        "requested_horizon_days":
                            horizon,

                        "origin_date":
                            current_origin.isoformat(),

                        "ensemble_family":
                            ensemble_family,

                        "component_count":
                            len(components),

                        "component_semantic_models":
                            ";".join(
                                components
                            ),

                        "selection_rule":
                            "PRIOR_ORIGIN_OOS_ONLY",
                    }
                )

                for fold_id, available in (
                    current_by_fold.items()
                ):

                    if not all(
                        component in available
                        for component in components
                    ):
                        continue

                    weights = np.asarray(
                        [
                            1.0
                            / (
                                prior_smape[
                                    component
                                ]
                                + EPSILON
                            )
                            for component
                            in components
                        ],
                        dtype=float,
                    )

                    weights = (
                        weights
                        / weights.sum()
                    )

                    component_rows = [
                        available[
                            component
                        ]
                        for component in components
                    ]

                    prediction = float(
                        np.dot(
                            weights,
                            np.asarray(
                                [
                                    row[
                                        "predicted_endpoint_price"
                                    ]
                                    for row
                                    in component_rows
                                ],
                                dtype=float,
                            ),
                        )
                    )

                    reference = component_rows[0]

                    row_metrics = metrics(
                        reference[
                            "origin_price"
                        ],
                        reference[
                            "actual_endpoint_price"
                        ],
                        prediction,
                    )

                    output.append(
                        {
                            "requested_horizon_days":
                                horizon,

                            "semantic_model_key":
                                (
                                    f"{ensemble_family}"
                                    f"|H{horizon}"
                                ),

                            "model_family":
                                ensemble_family,

                            "source_batch":
                                "LARGE_STEP_2",

                            "fold_id":
                                fold_id,

                            "canonical_product_id":
                                reference[
                                    "canonical_product_id"
                                ],

                            "origin_date":
                                current_origin.isoformat(),

                            "origin_price":
                                reference[
                                    "origin_price"
                                ],

                            "actual_endpoint_price":
                                reference[
                                    "actual_endpoint_price"
                                ],

                            "predicted_endpoint_price":
                                prediction,

                            "component_count":
                                len(
                                    components
                                ),

                            **row_metrics,
                        }
                    )

    return output, selection


def build_stability(rows):

    groups = defaultdict(list)

    for row in rows:

        groups[
            (
                row[
                    "requested_horizon_days"
                ],
                row[
                    "semantic_model_key"
                ],
                row[
                    "model_family"
                ],
            )
        ].append(row)

    output = []

    for (
        horizon,
        key,
        family,
    ), group_rows in sorted(
        groups.items()
    ):

        by_origin = defaultdict(list)
        by_product = defaultdict(list)

        for row in group_rows:

            by_origin[
                row[
                    "origin_date"
                ]
            ].append(
                row[
                    "smape"
                ]
            )

            by_product[
                row[
                    "canonical_product_id"
                ]
            ].append(
                row[
                    "smape"
                ]
            )

        origin_scores = [
            mean(values)
            for values
            in by_origin.values()
        ]

        product_scores = [
            mean(values)
            for values
            in by_product.values()
        ]

        output.append(
            {
                "requested_horizon_days":
                    horizon,

                "semantic_model_key":
                    key,

                "model_family":
                    family,

                "prediction_rows":
                    len(
                        group_rows
                    ),

                "origin_count":
                    len(
                        by_origin
                    ),

                "product_count":
                    len(
                        by_product
                    ),

                "mean_smape":
                    mean(
                        [
                            row["smape"]
                            for row
                            in group_rows
                        ]
                    ),

                "origin_smape_stddev":
                    std(
                        origin_scores
                    ),

                "product_smape_stddev":
                    std(
                        product_scores
                    ),

                "predicted_return_stddev":
                    std(
                        [
                            row[
                                "predicted_return"
                            ]
                            for row
                            in group_rows
                        ]
                    ),
            }
        )

    return output


def build_influence(rows):

    groups = defaultdict(list)

    for row in rows:

        groups[
            (
                row[
                    "requested_horizon_days"
                ],
                row[
                    "semantic_model_key"
                ],
                row[
                    "model_family"
                ],
            )
        ].append(row)

    output = []

    for (
        horizon,
        key,
        family,
    ), model_rows in sorted(
        groups.items()
    ):

        full = score(
            model_rows
        )

        by_product = defaultdict(list)

        for row in model_rows:

            by_product[
                row[
                    "canonical_product_id"
                ]
            ].append(row)

        for product_id, product_rows in (
            sorted(
                by_product.items()
            )
        ):

            remaining = [
                row
                for row in model_rows
                if (
                    row[
                        "canonical_product_id"
                    ]
                    != product_id
                )
            ]

            reduced = score(
                remaining
            )

            product_score = score(
                product_rows
            )

            output.append(
                {
                    "requested_horizon_days":
                        horizon,

                    "semantic_model_key":
                        key,

                    "model_family":
                        family,

                    "canonical_product_id":
                        product_id,

                    "product_prediction_rows":
                        len(
                            product_rows
                        ),

                    "product_smape":
                        product_score[
                            "SMAPE"
                        ],

                    "full_sample_smape":
                        full[
                            "SMAPE"
                        ],

                    "score_without_product_smape":
                        reduced[
                            "SMAPE"
                        ],

                    "score_exclusion_smape_delta":
                        (
                            float(
                                reduced[
                                    "SMAPE"
                                ]
                            )
                            - float(
                                full[
                                    "SMAPE"
                                ]
                            )
                        ),

                    "measure_type":
                        "OOS_SCORE_EXCLUSION_SENSITIVITY",

                    "persistent_exclusion_authorized":
                        "false",
                }
            )

    return output


def resolve_release_column(rows):

    for candidate in (
        "canonical_release_date",
        "release_date",
        "resolved_release_date",
        "historical_release_date",
    ):

        if candidate in rows[0]:
            return candidate

    fail(
        "unable to resolve release-date column"
    )


def feature_vector(
    feature,
    canonical_id,
    origin_date,
    history,
    release_dates,
):

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
            "no historical observations at origin"
        )

    origin_price = observations[-1][1]

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

        logs = np.log(
            prices
        )

        returns = []

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

            returns.append(
                (
                    logs[index]
                    - logs[
                        index - 1
                    ]
                )
                / math.sqrt(
                    float(
                        elapsed
                    )
                )
            )

        if not returns:
            raise ValueError(
                "no valid path intervals"
            )

        volatility = float(
            np.std(
                returns,
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
                    item
                    - first_date
                ).days
                for item
                in dates
            ],
            dtype=float,
        )

        slope, _ = np.polyfit(
            x,
            logs,
            1,
        )

        return np.asarray(
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

    raise ValueError(
        f"unsupported feature {feature}"
    )


def transform_target(
    origin,
    endpoint,
    elapsed_days,
    target,
):

    if target == "RAW_PRICE_CHANGE":
        return float(
            endpoint
            - origin
        )

    if target == "LOG_PRICE_CHANGE":
        return float(
            math.log(
                endpoint
                / origin
            )
        )

    if target == "RETURN":
        return float(
            (
                endpoint
                / origin
            ) - 1.0
        )

    if target == "ANNUALIZED_RETURN_WHERE_DEFINED":

        return float(
            (
                (
                    endpoint
                    / origin
                )
                ** (
                    365.0
                    / float(
                        elapsed_days
                    )
                )
            ) - 1.0
        )

    raise ValueError(
        f"unknown target {target}"
    )


def invert_target(
    origin,
    value,
    horizon,
    target,
):

    if target == "RAW_PRICE_CHANGE":

        predicted = (
            origin
            + value
        )

    elif target == "LOG_PRICE_CHANGE":

        predicted = (
            origin
            * math.exp(
                value
            )
        )

    elif target == "RETURN":

        predicted = (
            origin
            * (
                1.0
                + value
            )
        )

    elif target == "ANNUALIZED_RETURN_WHERE_DEFINED":

        base = (
            1.0
            + value
        )

        if base <= 0:
            raise ValueError(
                "annualized inversion <= 0"
            )

        predicted = (
            origin
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
        not math.isfinite(
            predicted
        )
        or predicted <= 0
    ):
        raise ValueError(
            "invalid predicted price"
        )

    return float(
        predicted
    )


def parse_semantic_key(key):

    parts = key.split("|")

    family = parts[0]

    if family in {
        "RIDGE_REGRESSION",
        "HUBER_REGRESSION",
        "RANDOM_FOREST",
        "GRADIENT_BOOSTING",
        "PEER_WEIGHTED_RETURN",
    }:

        if len(parts) != 4:
            fail(
                f"unexpected semantic key {key}"
            )

        return {
            "family":
                family,

            "feature":
                parts[1],

            "target":
                parts[2],

            "horizon":
                int(
                    parts[3][1:]
                ),
        }

    return {
        "family":
            family,

        "feature":
            "",

        "target":
            "",

        "horizon":
            int(
                parts[-1][1:]
            ),
    }


def estimator_for(family):

    if family == "RIDGE_REGRESSION":

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

    if family == "HUBER_REGRESSION":

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
        f"genuine LOPO unsupported family {family}"
    )


def genuine_lopo(
    config,
    canonical_rows,
    history_rows,
    folds,
    checkpoint_root,
):

    family = config[
        "family"
    ]

    if family not in {
        "RIDGE_REGRESSION",
        "HUBER_REGRESSION",
    }:

        return [], [
            {
                "semantic_model_key":
                    config[
                        "semantic_model_key"
                    ],

                "model_family":
                    family,

                "requested_horizon_days":
                    config[
                        "horizon"
                    ],

                "heldout_product_id":
                    "",

                "holdout_prediction_rows":
                    0,

                "holdout_smape":
                    "",

                "holdout_status":
                    "STRUCTURALLY_NOT_APPLICABLE_OR_NOT_POOLED_LEADER",
            }
        ]

    horizon = config[
        "horizon"
    ]

    feature = config[
        "feature"
    ]

    target = config[
        "target"
    ]

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

    for product_id in history:
        history[
            product_id
        ].sort(
            key=lambda item:
                item[0]
        )

    horizon_folds = [
        row
        for row in folds
        if (
            row[
                "horizon"
            ]
            == horizon
        )
    ]

    products = sorted(
        {
            row[
                "canonical_product_id"
            ]
            for row
            in horizon_folds
        }
    )

    feature_cache = {}

    def get_feature(
        product,
        origin,
    ):

        key = (
            product,
            origin,
        )

        if key not in feature_cache:

            feature_cache[
                key
            ] = feature_vector(
                feature,
                product,
                origin,
                history,
                release_dates,
            )

        return feature_cache[key]

    checkpoint_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        (
            f"START_GENUINE_LOPO={family}"
            f"|H={horizon}"
            f"|PRODUCTS={len(products)}"
        ),
        flush=True,
    )

    for index, heldout in enumerate(
        products,
        start=1,
    ):

        safe_product = (
            heldout
            .replace(
                ":",
                "_",
            )
        )

        checkpoint = (
            checkpoint_root
            / (
                f"{family}"
                f"__H{horizon}"
                f"__{safe_product}.json"
            )
        )

        if checkpoint.is_file():
            continue

        validation_folds = [
            row
            for row in horizon_folds
            if (
                row[
                    "canonical_product_id"
                ]
                == heldout
            )
        ]

        predictions = []
        skips = []

        for validation in validation_folds:

            origin = (
                validation[
                    "origin_date"
                ]
            )

            training = [
                row
                for row in horizon_folds
                if (
                    row[
                        "canonical_product_id"
                    ]
                    != heldout
                    and row[
                        "endpoint_date"
                    ]
                    <= origin
                )
            ]

            train_x = []
            train_y = []

            for row in training:

                try:

                    train_x.append(
                        get_feature(
                            row[
                                "canonical_product_id"
                            ],
                            row[
                                "origin_date"
                            ],
                        )
                    )

                    train_y.append(
                        transform_target(
                            row[
                                "origin_price"
                            ],
                            row[
                                "endpoint_price"
                            ],
                            row[
                                "elapsed_days"
                            ],
                            target,
                        )
                    )

                except Exception:
                    continue

            if len(train_x) < MIN_SUPERVISED_ROWS:

                skips.append(
                    {
                        "fold_id":
                            validation[
                                "fold_id"
                            ],

                        "reason":
                            (
                                "INSUFFICIENT_LOPO_TRAINING_ROWS:"
                                f"{len(train_x)}"
                            ),
                    }
                )

                continue

            try:

                estimator = estimator_for(
                    family
                )

                estimator.fit(
                    np.vstack(
                        train_x
                    ),
                    np.asarray(
                        train_y,
                        dtype=float,
                    ),
                )

                x_validation = get_feature(
                    heldout,
                    origin,
                )

                predicted_target = float(
                    estimator.predict(
                        x_validation.reshape(
                            1,
                            -1,
                        )
                    )[0]
                )

                predicted_price = invert_target(
                    validation[
                        "origin_price"
                    ],
                    predicted_target,
                    horizon,
                    target,
                )

                row_metrics = metrics(
                    validation[
                        "origin_price"
                    ],
                    validation[
                        "endpoint_price"
                    ],
                    predicted_price,
                )

            except Exception as exc:

                skips.append(
                    {
                        "fold_id":
                            validation[
                                "fold_id"
                            ],

                        "reason":
                            (
                                "LOPO_FAILURE:"
                                + str(exc)
                            ),
                    }
                )

                continue

            predictions.append(
                {
                    "semantic_model_key":
                        config[
                            "semantic_model_key"
                        ],

                    "model_family":
                        family,

                    "feature_variant":
                        feature,

                    "target_transformation":
                        target,

                    "requested_horizon_days":
                        horizon,

                    "heldout_product_id":
                        heldout,

                    "fold_id":
                        validation[
                            "fold_id"
                        ],

                    "origin_date":
                        origin.isoformat(),

                    "origin_price":
                        validation[
                            "origin_price"
                        ],

                    "actual_endpoint_price":
                        validation[
                            "endpoint_price"
                        ],

                    "predicted_endpoint_price":
                        predicted_price,

                    **row_metrics,
                }
            )

        atomic_json(
            checkpoint,
            {
                "heldout_product_id":
                    heldout,

                "predictions":
                    predictions,

                "skips":
                    skips,
            },
        )

        if (
            index % 10 == 0
            or index == len(products)
        ):
            print(
                (
                    f"LOPO_PROGRESS={index}/{len(products)}"
                    f"|MODEL={family}"
                    f"|H={horizon}"
                ),
                flush=True,
            )

    all_predictions = []

    for checkpoint in sorted(
        checkpoint_root.glob(
            f"{family}__H{horizon}__*.json"
        )
    ):

        payload = json.loads(
            checkpoint.read_text(
                encoding="utf-8"
            )
        )

        all_predictions.extend(
            payload[
                "predictions"
            ]
        )

    by_product = defaultdict(
        list
    )

    for row in all_predictions:

        by_product[
            row[
                "heldout_product_id"
            ]
        ].append(row)

    status = []

    for product in products:

        rows = by_product.get(
            product,
            [],
        )

        product_score = score(
            rows
        )

        status.append(
            {
                "semantic_model_key":
                    config[
                        "semantic_model_key"
                    ],

                "model_family":
                    family,

                "requested_horizon_days":
                    horizon,

                "heldout_product_id":
                    product,

                "holdout_prediction_rows":
                    product_score[
                        "prediction_rows"
                    ],

                "holdout_smape":
                    product_score[
                        "SMAPE"
                    ],

                "holdout_status":
                    (
                        "GENUINE_LEAVE_ONE_PRODUCT_OUT"
                        if rows
                        else "NO_VALID_LOPO_PREDICTIONS"
                    ),
            }
        )

    return (
        all_predictions,
        status,
    )


def main():

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
        "--diagnostics-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--base-package",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--lopo-checkpoint-root",
        type=Path,
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

    empirical_rows = read_zip_csv(
        args.diagnostics_package,
        "precollector_empirical_eligibility_diagnostics_v1.csv",
    )

    base_raw = read_zip_csv(
        args.base_package,
        "precollector_base_common_fold_prediction_ledger_v1.csv",
    )

    base_summary = read_zip_json(
        args.base_package,
        "precollector_base_tournament_reconciliation_summary_v1.json",
    )

    if len(canonical_rows) != 131:
        fail(
            "canonical product count != 131"
        )

    if len(empirical_rows) != 131:
        fail(
            "empirical diagnostic count != 131"
        )

    if (
        base_summary[
            "status"
        ]
        !=
        "PASS_PRECOLLECTOR_COMPLETE_BASE_TEMPORAL_OOS_TOURNAMENT_V1"
    ):
        fail(
            "complete base tournament did not PASS"
        )

    base_rows = [
        normalize_base_row(
            row
        )
        for row in base_raw
    ]

    if not base_rows:
        fail(
            "base common-fold prediction ledger empty"
        )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "PHASE_A_NESTED_OOS_ENSEMBLES",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    (
        ensemble_rows,
        ensemble_selection,
    ) = nested_ensembles(
        base_rows
    )

    if not ensemble_rows:
        fail(
            "no nested ensemble predictions generated"
        )

    # ========================================================================
    # Restrict comparison to folds where BOTH ensemble families exist.
    # ========================================================================

    valid_folds = {}

    for horizon in HORIZONS:

        route = {
            row[
                "fold_id"
            ]
            for row in ensemble_rows
            if (
                row[
                    "requested_horizon_days"
                ]
                == horizon
                and row[
                    "model_family"
                ]
                == "ROUTE_ENSEMBLE"
            )
        }

        global_set = {
            row[
                "fold_id"
            ]
            for row in ensemble_rows
            if (
                row[
                    "requested_horizon_days"
                ]
                == horizon
                and row[
                    "model_family"
                ]
                == "GLOBAL_ENSEMBLE"
            )
        }

        intersection = (
            route
            & global_set
        )

        if not intersection:
            fail(
                f"no paired ensemble folds at H{horizon}"
            )

        valid_folds[
            horizon
        ] = intersection

    diagnostic_rows = [
        row
        for row in (
            base_rows
            + ensemble_rows
        )
        if (
            row[
                "fold_id"
            ]
            in valid_folds[
                row[
                    "requested_horizon_days"
                ]
            ]
        )
    ]

    diagnostic_groups = defaultdict(
        list
    )

    for row in diagnostic_rows:

        diagnostic_groups[
            (
                row[
                    "requested_horizon_days"
                ],
                row[
                    "semantic_model_key"
                ],
                row[
                    "model_family"
                ],
            )
        ].append(row)

    diagnostic_scorecard = []

    for (
        horizon,
        semantic_key,
        family,
    ), rows in sorted(
        diagnostic_groups.items()
    ):

        row_score = score(
            rows
        )

        diagnostic_scorecard.append(
            {
                "requested_horizon_days":
                    horizon,

                "semantic_model_key":
                    semantic_key,

                "model_family":
                    family,

                **row_score,

                "status":
                    "DIAGNOSTIC_ONLY_NOT_FINAL_MODEL",
            }
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
        "PHASE_B_STABILITY_AND_INFLUENCE",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    stability_rows = build_stability(
        diagnostic_rows
    )

    influence_rows = build_influence(
        diagnostic_rows
    )

    # ========================================================================
    # Genuine product holdout for applicable pooled horizon leaders.
    # ========================================================================

    folds = []

    for raw in fold_rows_raw:

        folds.append(
            {
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

                "elapsed_days":
                    int(
                        raw[
                            "actual_elapsed_days"
                        ]
                    ),
            }
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
        "PHASE_C_GENUINE_PRODUCT_HOLDOUT",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    leader_configs = []

    for horizon in HORIZONS:

        leader = (
            base_summary[
                "descriptive_best_paired_base_models"
            ][
                str(horizon)
            ]
        )

        semantic_key = (
            leader[
                "semantic_model_key"
            ]
        )

        parsed = parse_semantic_key(
            semantic_key
        )

        parsed[
            "semantic_model_key"
        ] = semantic_key

        leader_configs.append(
            parsed
        )

    all_lopo_predictions = []
    all_holdout_status = []

    for config in leader_configs:

        (
            lopo_predictions,
            holdout_status,
        ) = genuine_lopo(
            config,
            canonical_rows,
            history_rows,
            folds,
            args.lopo_checkpoint_root,
        )

        all_lopo_predictions.extend(
            lopo_predictions
        )

        all_holdout_status.extend(
            holdout_status
        )

    # ========================================================================
    # Descriptive rankings
    # ========================================================================

    ranking_rows = []

    for horizon in HORIZONS:

        candidates = [
            row
            for row in diagnostic_scorecard
            if (
                row[
                    "requested_horizon_days"
                ]
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
                abs(
                    float(
                        row[
                            "BIAS"
                        ]
                    )
                ),
            )
        )

        for rank, row in enumerate(
            candidates,
            start=1,
        ):

            ranking_rows.append(
                {
                    "requested_horizon_days":
                        horizon,

                    "diagnostic_rank":
                        rank,

                    "semantic_model_key":
                        row[
                            "semantic_model_key"
                        ],

                    "model_family":
                        row[
                            "model_family"
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
                        "DESCRIPTIVE_ROBUSTNESS_RANK_NOT_FINAL_WINNER",
                }
            )

    # ========================================================================
    # 131-product treatment proposal ledger.
    #
    # Important:
    # This diagnostic stage assigns ZERO persistent adverse treatments.
    # ========================================================================

    empirical_by_product = {
        clean(
            row[
                "canonical_product_id"
            ]
        ):
            row
        for row in empirical_rows
    }

    influence_by_product = defaultdict(
        list
    )

    for row in influence_rows:

        influence_by_product[
            row[
                "canonical_product_id"
            ]
        ].append(row)

    holdout_by_product = defaultdict(
        list
    )

    for row in all_holdout_status:

        product = clean(
            row.get(
                "heldout_product_id"
            )
        )

        if product:

            holdout_by_product[
                product
            ].append(row)

    treatment_rows = []

    for canonical in canonical_rows:

        product_id = clean(
            canonical[
                "canonical_product_id"
            ]
        )

        empirical = (
            empirical_by_product[
                product_id
            ]
        )

        product_influence = (
            influence_by_product.get(
                product_id,
                [],
            )
        )

        product_holdout = (
            holdout_by_product.get(
                product_id,
                [],
            )
        )

        adverse_sensitivity_rows = [
            row
            for row in product_influence
            if (
                float(
                    row[
                        "score_exclusion_smape_delta"
                    ]
                )
                < 0
            )
        ]

        treatment_rows.append(
            {
                "canonical_product_id":
                    product_id,

                "product_name":
                    clean(
                        canonical[
                            "product_name"
                        ]
                    ),

                "canonical_membership":
                    "true",

                "evidence_domains_present":
                    empirical[
                        "evidence_domains_present"
                    ],

                "history_observation_count":
                    empirical[
                        "history_observation_count"
                    ],

                "accepted_listing_count":
                    empirical[
                        "accepted_listing_count"
                    ],

                "unique_seller_count":
                    empirical[
                        "unique_seller_count"
                    ],

                "oos_influence_diagnostic_rows":
                    len(
                        product_influence
                    ),

                "adverse_score_sensitivity_rows":
                    len(
                        adverse_sensitivity_rows
                    ),

                "genuine_holdout_diagnostic_rows":
                    len(
                        product_holdout
                    ),

                "proposed_model_status":
                    "MODEL_ELIGIBLE",

                "persistent_treatment_assigned":
                    "false",

                "persistent_exclusion_assigned":
                    "false",

                "owner_review_required":
                    "false",

                "owner_review_status":
                    "NO_PERSISTENT_ADVERSE_TREATMENT_PROPOSED",

                "diagnostic_note":
                    (
                        "Diagnostics captured; "
                        "no automatic adverse treatment permitted."
                    ),
            }
        )

    if len(treatment_rows) != 131:
        fail(
            "treatment ledger != 131 products"
        )

    # ========================================================================
    # Outputs
    # ========================================================================

    root = args.output_root.resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    ensemble_prediction_path = (
        root
        / "precollector_nested_ensemble_oos_predictions_v1.csv"
    )

    ensemble_selection_path = (
        root
        / "precollector_nested_ensemble_selection_ledger_v1.csv"
    )

    robustness_scorecard_path = (
        root
        / "precollector_ensemble_base_robustness_scorecard_v1.csv"
    )

    stability_path = (
        root
        / "precollector_model_stability_ledger_v1.csv"
    )

    influence_path = (
        root
        / "precollector_product_influence_sensitivity_v1.csv"
    )

    lopo_prediction_path = (
        root
        / "precollector_genuine_product_holdout_predictions_v1.csv"
    )

    holdout_path = (
        root
        / "precollector_product_holdout_ledger_v1.csv"
    )

    treatment_path = (
        root
        / "precollector_model_treatment_proposal_ledger_v1.csv"
    )

    ranking_path = (
        root
        / "precollector_robustness_diagnostic_ranking_v1.csv"
    )

    summary_path = (
        root
        / "precollector_large_step_2_summary_v1.json"
    )

    write_csv(
        ensemble_prediction_path,
        ensemble_rows,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "source_batch",
            "fold_id",
            "canonical_product_id",
            "origin_date",
            "origin_price",
            "actual_endpoint_price",
            "predicted_endpoint_price",
            "component_count",
            "error",
            "absolute_error",
            "squared_error",
            "smape",
            "actual_return",
            "predicted_return",
            "direction_correct",
            "downside_error",
        ],
    )

    write_csv(
        ensemble_selection_path,
        ensemble_selection,
        [
            "requested_horizon_days",
            "origin_date",
            "ensemble_family",
            "component_count",
            "component_semantic_models",
            "selection_rule",
        ],
    )

    write_csv(
        robustness_scorecard_path,
        diagnostic_scorecard,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "prediction_rows",
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
        stability_path,
        stability_rows,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "prediction_rows",
            "origin_count",
            "product_count",
            "mean_smape",
            "origin_smape_stddev",
            "product_smape_stddev",
            "predicted_return_stddev",
        ],
    )

    write_csv(
        influence_path,
        influence_rows,
        [
            "requested_horizon_days",
            "semantic_model_key",
            "model_family",
            "canonical_product_id",
            "product_prediction_rows",
            "product_smape",
            "full_sample_smape",
            "score_without_product_smape",
            "score_exclusion_smape_delta",
            "measure_type",
            "persistent_exclusion_authorized",
        ],
    )

    write_csv(
        lopo_prediction_path,
        all_lopo_predictions,
        [
            "semantic_model_key",
            "model_family",
            "feature_variant",
            "target_transformation",
            "requested_horizon_days",
            "heldout_product_id",
            "fold_id",
            "origin_date",
            "origin_price",
            "actual_endpoint_price",
            "predicted_endpoint_price",
            "error",
            "absolute_error",
            "squared_error",
            "smape",
            "actual_return",
            "predicted_return",
            "direction_correct",
            "downside_error",
        ],
    )

    holdout_fields = sorted(
        {
            key
            for row in all_holdout_status
            for key in row.keys()
        }
    )

    write_csv(
        holdout_path,
        all_holdout_status,
        holdout_fields,
    )

    write_csv(
        treatment_path,
        treatment_rows,
        [
            "canonical_product_id",
            "product_name",
            "canonical_membership",
            "evidence_domains_present",
            "history_observation_count",
            "accepted_listing_count",
            "unique_seller_count",
            "oos_influence_diagnostic_rows",
            "adverse_score_sensitivity_rows",
            "genuine_holdout_diagnostic_rows",
            "proposed_model_status",
            "persistent_treatment_assigned",
            "persistent_exclusion_assigned",
            "owner_review_required",
            "owner_review_status",
            "diagnostic_note",
        ],
    )

    write_csv(
        ranking_path,
        ranking_rows,
        [
            "requested_horizon_days",
            "diagnostic_rank",
            "semantic_model_key",
            "model_family",
            "SMAPE",
            "MAE",
            "RMSE",
            "BIAS",
            "DIRECTIONAL_ACCURACY",
            "DOWNSIDE_ERROR",
            "status",
        ],
    )

    genuine_holdout_products = len(
        {
            row[
                "heldout_product_id"
            ]
            for row in all_lopo_predictions
        }
    )

    descriptive_leaders = {}

    for horizon in HORIZONS:

        top = next(
            row
            for row in ranking_rows
            if (
                row[
                    "requested_horizon_days"
                ]
                == horizon
                and row[
                    "diagnostic_rank"
                ]
                == 1
            )
        )

        descriptive_leaders[
            str(horizon)
        ] = {
            "semantic_model_key":
                top[
                    "semantic_model_key"
                ],

            "model_family":
                top[
                    "model_family"
                ],

            "SMAPE":
                top[
                    "SMAPE"
                ],

            "MAE":
                top[
                    "MAE"
                ],

            "status":
                "DESCRIPTIVE_ROBUSTNESS_LEADER_NOT_FINAL_WINNER",
        }

    summary = {
        "status":
            "PASS_PRECOLLECTOR_LARGE_STEP_2_ENSEMBLE_ROBUSTNESS_V1",

        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "canonical_products":
            131,

        "base_model_families":
            11,

        "ensemble_families":
            2,

        "ensemble_prediction_rows":
            len(
                ensemble_rows
            ),

        "stability_rows":
            len(
                stability_rows
            ),

        "influence_rows":
            len(
                influence_rows
            ),

        "genuine_lopo_prediction_rows":
            len(
                all_lopo_predictions
            ),

        "genuine_holdout_products":
            genuine_holdout_products,

        "treatment_proposal_rows":
            131,

        "descriptive_robustness_leaders":
            descriptive_leaders,

        "persistent_treatments_assigned":
            0,

        "persistent_exclusions_assigned":
            0,

        "final_model_selected":
            False,

        "production_model_execution_authorized":
            False,

        "forecast_execution_authorized":
            False,

        "monte_carlo_execution_authorized":
            False,

        "ranking_execution_authorized":
            False,

        "purchase_analysis_authorized":
            False,

        "authorized_next_large_step":
            "FINAL_MODEL_CERTIFICATION_AND_FORECAST_SCENARIO_CONSTRUCTION",
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
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
        "PASS_PRECOLLECTOR_LARGE_STEP_2_ENSEMBLE_ROBUSTNESS_V1",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        f"ENSEMBLE_PREDICTION_ROWS={len(ensemble_rows)}",
        flush=True,
    )

    print(
        f"STABILITY_ROWS={len(stability_rows)}",
        flush=True,
    )

    print(
        f"INFLUENCE_ROWS={len(influence_rows)}",
        flush=True,
    )

    print(
        f"GENUINE_LOPO_PREDICTION_ROWS={len(all_lopo_predictions)}",
        flush=True,
    )

    print(
        f"GENUINE_HOLDOUT_PRODUCTS={genuine_holdout_products}",
        flush=True,
    )

    print(
        "TREATMENT_PROPOSAL_ROWS=131",
        flush=True,
    )

    print(
        "PERSISTENT_TREATMENTS_ASSIGNED=0",
        flush=True,
    )

    print(
        "PERSISTENT_EXCLUSIONS_ASSIGNED=0",
        flush=True,
    )

    for horizon in HORIZONS:

        leader = descriptive_leaders[
            str(horizon)
        ]

        print(
            (
                f"HORIZON_{horizon}_ROBUSTNESS_LEADER="
                f"{leader['semantic_model_key']}|"
                f"SMAPE={float(leader['SMAPE']):.8f}|"
                f"MAE={float(leader['MAE']):.8f}"
            ),
            flush=True,
        )

    print(
        "FINAL_MODEL_SELECTED=FALSE",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )