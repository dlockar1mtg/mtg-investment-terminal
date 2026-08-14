from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from datetime import date
from pathlib import Path

import numpy as np


DAYS_PER_YEAR = 365.0


BASELINES = (
    "LAST_VALUE",
    "GLOBAL_REALIZED_MEDIAN",
    "EXACT_PEER_TRAJECTORY",
)


NUMERIC_FEATURE_SETS = {
    "ANCHOR_PLUS_MOMENTUM_OLS": (
        "own_latest_interval_annualized_log_return",
        "own_recent_minus_median_momentum",
    ),

    "ANCHOR_PLUS_BEHAVIOR_OLS": (
        "own_full_history_annualized_log_return",
        "own_log_price_slope_annualized",
        "own_latest_interval_annualized_log_return",
        "own_recent_minus_median_momentum",
        "own_interval_volatility",
        "own_downside_semideviation",
        "own_maximum_drawdown",
        "own_positive_interval_fraction",
        "own_negative_interval_fraction",
    ),

    "ANCHOR_PLUS_BEHAVIOR_VALUATION_OLS": (
        "own_full_history_annualized_log_return",
        "own_log_price_slope_annualized",
        "own_latest_interval_annualized_log_return",
        "own_recent_minus_median_momentum",
        "own_interval_volatility",
        "own_downside_semideviation",
        "own_maximum_drawdown",
        "own_positive_interval_fraction",
        "own_negative_interval_fraction",
        "current_to_own_historical_median_ratio",
        "current_to_own_historical_high_ratio",
        "current_to_own_historical_low_ratio",
        "current_to_exact_peer_median_price_ratio",
        "current_vs_exact_peer_median_log_valuation",
    ),

    "ANCHOR_PLUS_FULL_STRUCTURE_OLS": (
        "own_full_history_annualized_log_return",
        "own_log_price_slope_annualized",
        "own_latest_interval_annualized_log_return",
        "own_recent_minus_median_momentum",
        "own_interval_volatility",
        "own_downside_semideviation",
        "own_maximum_drawdown",
        "own_positive_interval_fraction",
        "own_negative_interval_fraction",
        "current_to_own_historical_median_ratio",
        "current_to_own_historical_high_ratio",
        "current_to_own_historical_low_ratio",
        "current_to_exact_peer_median_price_ratio",
        "current_vs_exact_peer_median_log_valuation",
    ),
}


STRUCTURAL_FIELDS = (
    "finish",
    "detailed_finish",
    "product_family",
    "sealed_configuration",
)


MULTIVARIATE_MODELS = tuple(
    NUMERIC_FEATURE_SETS.keys()
)


ALL_MODELS = (
    *BASELINES,
    *MULTIVARIATE_MODELS,
)


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def as_float(
    value: object,
) -> float | None:

    text = clean(value)

    if not text:
        return None

    try:
        result = float(text)
    except ValueError:
        return None

    if not math.isfinite(result):
        return None

    return result


def as_date(
    value: object,
) -> date:

    text = clean(value)

    if not text:
        fail(
            "blank governed date"
        )

    return date.fromisoformat(
        text[:10]
    )


def read_csv(
    path: Path,
) -> list[dict[str, str]]:

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


def safe_price(
    origin_price: float,
    annualized_log_return: float,
    days: int,
) -> float | None:

    try:

        exponent = (
            annualized_log_return
            *
            (
                days
                /
                DAYS_PER_YEAR
            )
        )

        result = (
            origin_price
            *
            math.exp(
                exponent
            )
        )

    except OverflowError:
        return None

    if (
        not math.isfinite(result)
        or
        result <= 0
    ):
        return None

    return result


def smape(
    actual: float,
    predicted: float,
) -> float:

    denominator = (
        abs(actual)
        +
        abs(predicted)
    )

    if denominator == 0:
        return 0.0

    return (
        2.0
        *
        abs(
            predicted
            -
            actual
        )
        /
        denominator
    )


def average_ranks(
    values: list[float],
) -> list[float]:

    indexed = sorted(
        enumerate(
            values
        ),
        key=lambda pair:
            pair[1],
    )

    ranks = [
        0.0
        for _
        in values
    ]

    start = 0

    while start < len(
        indexed
    ):

        end = start + 1

        while (
            end
            <
            len(
                indexed
            )
            and
            indexed[end][1]
            ==
            indexed[start][1]
        ):
            end += 1

        average = (
            (
                start + 1
            )
            +
            end
        ) / 2.0

        for position in range(
            start,
            end,
        ):

            original_index = indexed[
                position
            ][0]

            ranks[
                original_index
            ] = average

        start = end

    return ranks


def pearson(
    x: list[float],
    y: list[float],
) -> float | None:

    if len(x) != len(y):
        fail(
            "correlation length mismatch"
        )

    if len(x) < 2:
        return None

    mean_x = statistics.fmean(
        x
    )

    mean_y = statistics.fmean(
        y
    )

    numerator = sum(
        (
            a
            -
            mean_x
        )
        *
        (
            b
            -
            mean_y
        )
        for a, b
        in zip(
            x,
            y,
        )
    )

    denominator_x = math.sqrt(
        sum(
            (
                a
                -
                mean_x
            ) ** 2
            for a
            in x
        )
    )

    denominator_y = math.sqrt(
        sum(
            (
                b
                -
                mean_y
            ) ** 2
            for b
            in y
        )
    )

    denominator = (
        denominator_x
        *
        denominator_y
    )

    if denominator == 0:
        return None

    return (
        numerator
        /
        denominator
    )


def spearman(
    predicted: list[float],
    actual: list[float],
) -> float | None:

    return pearson(
        average_ranks(
            predicted
        ),
        average_ranks(
            actual
        ),
    )


def quartile_spread(
    predicted: list[float],
    actual: list[float],
) -> float | None:

    if len(predicted) != len(actual):
        fail(
            "quartile length mismatch"
        )

    if len(predicted) < 4:
        return None

    pairs = sorted(
        zip(
            predicted,
            actual,
        ),
        key=lambda pair:
            pair[0],
    )

    group_size = (
        len(
            pairs
        )
        //
        4
    )

    if group_size < 1:
        return None

    bottom = [
        pair[1]
        for pair
        in pairs[
            :group_size
        ]
    ]

    top = [
        pair[1]
        for pair
        in pairs[
            -group_size:
        ]
    ]

    return (
        statistics.fmean(
            top
        )
        -
        statistics.fmean(
            bottom
        )
    )


def train_median(
    values: list[float | None],
) -> float:

    present = [
        float(
            value
        )
        for value
        in values
        if value is not None
    ]

    if not present:
        return 0.0

    return statistics.median(
        present
    )


def numeric_design(
    train_rows: list[dict[str, object]],
    prediction_rows: list[dict[str, object]],
    fields: tuple[str, ...],
) -> tuple[
    np.ndarray,
    np.ndarray,
    list[str],
]:

    train_columns: list[
        list[float]
    ] = []

    prediction_columns: list[
        list[float]
    ] = []

    names: list[str] = []

    for field in fields:

        raw_train = [
            row[
                field
            ]
            for row
            in train_rows
        ]

        raw_prediction = [
            row[
                field
            ]
            for row
            in prediction_rows
        ]

        median = train_median(
            raw_train
        )

        imputed_train = [
            (
                median
                if value is None
                else float(
                    value
                )
            )
            for value
            in raw_train
        ]

        imputed_prediction = [
            (
                median
                if value is None
                else float(
                    value
                )
            )
            for value
            in raw_prediction
        ]

        mean = statistics.fmean(
            imputed_train
        )

        if len(
            imputed_train
        ) >= 2:

            std = statistics.pstdev(
                imputed_train
            )

        else:

            std = 0.0

        if std > 0:

            standardized_train = [
                (
                    value
                    -
                    mean
                )
                /
                std
                for value
                in imputed_train
            ]

            standardized_prediction = [
                (
                    value
                    -
                    mean
                )
                /
                std
                for value
                in imputed_prediction
            ]

        else:

            standardized_train = [
                0.0
                for _
                in imputed_train
            ]

            standardized_prediction = [
                0.0
                for _
                in imputed_prediction
            ]

        missing_train = [
            1.0
            if value is None
            else 0.0
            for value
            in raw_train
        ]

        missing_prediction = [
            1.0
            if value is None
            else 0.0
            for value
            in raw_prediction
        ]

        train_columns.append(
            standardized_train
        )

        prediction_columns.append(
            standardized_prediction
        )

        names.append(
            field
        )

        if any(
            value == 1.0
            for value
            in missing_train
        ):

            train_columns.append(
                missing_train
            )

            prediction_columns.append(
                missing_prediction
            )

            names.append(
                field
                +
                "__MISSING"
            )

    if not train_columns:

        return (
            np.empty(
                (
                    len(
                        train_rows
                    ),
                    0,
                )
            ),
            np.empty(
                (
                    len(
                        prediction_rows
                    ),
                    0,
                )
            ),
            [],
        )

    train_matrix = np.asarray(
        train_columns,
        dtype=float,
    ).T

    prediction_matrix = np.asarray(
        prediction_columns,
        dtype=float,
    ).T

    return (
        train_matrix,
        prediction_matrix,
        names,
    )


def append_structure(
    train_matrix: np.ndarray,
    prediction_matrix: np.ndarray,
    train_rows: list[dict[str, object]],
    prediction_rows: list[dict[str, object]],
    names: list[str],
) -> tuple[
    np.ndarray,
    np.ndarray,
    list[str],
]:

    additional_train: list[
        list[float]
    ] = []

    additional_prediction: list[
        list[float]
    ] = []

    additional_names: list[str] = []

    for field in STRUCTURAL_FIELDS:

        categories = sorted(
            {
                clean(
                    row[
                        field
                    ]
                )
                for row
                in train_rows
                if clean(
                    row[
                        field
                    ]
                )
            }
        )

        # Reference coding:
        # omit first category, avoiding a deterministic dummy-variable trap
        # with the fitted intercept.
        for category in categories[
            1:
        ]:

            additional_train.append(
                [
                    1.0
                    if clean(
                        row[
                            field
                        ]
                    )
                    ==
                    category
                    else 0.0
                    for row
                    in train_rows
                ]
            )

            additional_prediction.append(
                [
                    1.0
                    if clean(
                        row[
                            field
                        ]
                    )
                    ==
                    category
                    else 0.0
                    for row
                    in prediction_rows
                ]
            )

            additional_names.append(
                field
                +
                "="
                +
                category
            )

    if additional_train:

        structure_train = np.asarray(
            additional_train,
            dtype=float,
        ).T

        structure_prediction = np.asarray(
            additional_prediction,
            dtype=float,
        ).T

        train_matrix = np.column_stack(
            (
                train_matrix,
                structure_train,
            )
        )

        prediction_matrix = np.column_stack(
            (
                prediction_matrix,
                structure_prediction,
            )
        )

        names = (
            list(
                names
            )
            +
            additional_names
        )

    return (
        train_matrix,
        prediction_matrix,
        names,
    )


def fit_residual_ols(
    train_rows: list[dict[str, object]],
    prediction_rows: list[dict[str, object]],
    model_name: str,
) -> tuple[
    list[float] | None,
    int,
]:

    # No learned model exists before any outcomes have matured.
    # Return unavailable for this historical origin rather than trying
    # to estimate training statistics from an empty evidence set.
    if not train_rows or not prediction_rows:
        return (
            None,
            0,
        )

    numeric_fields = NUMERIC_FEATURE_SETS[
        model_name
    ]

    x_train, x_prediction, names = numeric_design(
        train_rows,
        prediction_rows,
        numeric_fields,
    )

    if (
        model_name
        ==
        "ANCHOR_PLUS_FULL_STRUCTURE_OLS"
    ):

        (
            x_train,
            x_prediction,
            names,
        ) = append_structure(
            x_train,
            x_prediction,
            train_rows,
            prediction_rows,
            names,
        )

    # Add fitted intercept.
    x_train = np.column_stack(
        (
            np.ones(
                len(
                    train_rows
                )
            ),
            x_train,
        )
    )

    x_prediction = np.column_stack(
        (
            np.ones(
                len(
                    prediction_rows
                )
            ),
            x_prediction,
        )
    )

    parameter_count = x_train.shape[
        1
    ]

    # Fail this origin for this candidate when the expanding training set does
    # not contain more observations than fitted parameters.
    #
    # This is an identifiability/data-support rule, not a model-performance
    # threshold.
    if (
        len(
            train_rows
        )
        <=
        parameter_count
    ):

        return (
            None,
            parameter_count,
        )

    y = np.asarray(
        [
            float(
                row[
                    "actual_return"
                ]
            )
            -
            float(
                row[
                    "peer_trajectory"
                ]
            )
            for row
            in train_rows
        ],
        dtype=float,
    )

    coefficients, _, rank, _ = np.linalg.lstsq(
        x_train,
        y,
        rcond=None,
    )

    if rank <= 0:
        return (
            None,
            parameter_count,
        )

    adjustments = (
        x_prediction
        @
        coefficients
    )

    results = [
        float(
            adjustment
        )
        for adjustment
        in adjustments
    ]

    if not all(
        math.isfinite(
            value
        )
        for value
        in results
    ):
        return (
            None,
            parameter_count,
        )

    return (
        results,
        parameter_count,
    )


parser = argparse.ArgumentParser()

parser.add_argument(
    "--matrix",
    required=True,
)

parser.add_argument(
    "--run-root",
    required=True,
)

parser.add_argument(
    "--expected-rows",
    required=True,
    type=int,
)

args = parser.parse_args()


source_rows = read_csv(
    Path(
        args.matrix
    )
)

if len(
    source_rows
) != args.expected_rows:

    fail(
        "temporal matrix row drift: "
        f"expected={args.expected_rows}, "
        f"actual={len(source_rows)}"
    )


# ---------------------------------------------------------------------------
# Parse governed matrix.
# ---------------------------------------------------------------------------

numeric_fields_all = sorted(
    {
        field
        for fields
        in NUMERIC_FEATURE_SETS.values()
        for field
        in fields
    }
)


rows: list[
    dict[str, object]
] = []


for raw in source_rows:

    origin_price = as_float(
        raw.get(
            "origin_price_usd"
        )
    )

    endpoint_price = as_float(
        raw.get(
            "target_endpoint_price_usd"
        )
    )

    actual_return = as_float(
        raw.get(
            "target_realized_annualized_log_return"
        )
    )

    peer_trajectory = as_float(
        raw.get(
            "exact_peer_median_annualized_log_return"
        )
    )

    if (
        origin_price is None
        or
        origin_price <= 0
        or
        endpoint_price is None
        or
        endpoint_price <= 0
        or
        actual_return is None
    ):
        fail(
            "invalid governed target row"
        )

    row: dict[
        str,
        object
    ] = {
        "product_id":
            clean(
                raw.get(
                    "secret_lair_id"
                )
            ),

        "product_name":
            clean(
                raw.get(
                    "product_name"
                )
            ),

        "origin_date":
            as_date(
                raw.get(
                    "origin_date"
                )
            ),

        "endpoint_date":
            as_date(
                raw.get(
                    "target_endpoint_date"
                )
            ),

        "origin_price":
            origin_price,

        "endpoint_price":
            endpoint_price,

        "realized_days":
            int(
                clean(
                    raw.get(
                        "target_realized_days"
                    )
                )
            ),

        "actual_return":
            actual_return,

        "peer_trajectory":
            peer_trajectory,
    }

    for field in numeric_fields_all:

        row[
            field
        ] = as_float(
            raw.get(
                field
            )
        )

    for field in STRUCTURAL_FIELDS:

        row[
            field
        ] = clean(
            raw.get(
                field
            )
        )

    rows.append(
        row
    )


# ---------------------------------------------------------------------------
# Work by forecast origin.
# ---------------------------------------------------------------------------

origin_dates = sorted(
    {
        row[
            "origin_date"
        ]
        for row
        in rows
    }
)


predictions: list[
    dict[str, object]
] = []


for origin_date in origin_dates:

    targets = [
        row
        for row
        in rows
        if row[
            "origin_date"
        ]
        ==
        origin_date
    ]

    matured = [
        row
        for row
        in rows
        if row[
            "endpoint_date"
        ]
        <=
        origin_date
    ]

    # Multivariate residual models require exact-peer anchor values in both
    # training and prediction records.
    multivariate_train = [
        row
        for row
        in matured
        if row[
            "peer_trajectory"
        ]
        is not None
    ]

    multivariate_targets = [
        row
        for row
        in targets
        if row[
            "peer_trajectory"
        ]
        is not None
    ]

    adjustments_by_model: dict[
        str,
        dict[str, float]
    ] = {
        model_name:
            {}
        for model_name
        in MULTIVARIATE_MODELS
    }

    parameter_counts: dict[
        str,
        int
    ] = {
        model_name:
            0
        for model_name
        in MULTIVARIATE_MODELS
    }

    if multivariate_targets:

        for model_name in MULTIVARIATE_MODELS:

            (
                adjustments,
                parameter_count,
            ) = fit_residual_ols(
                multivariate_train,
                multivariate_targets,
                model_name,
            )

            parameter_counts[
                model_name
            ] = parameter_count

            if adjustments is not None:

                for target, adjustment in zip(
                    multivariate_targets,
                    adjustments,
                ):

                    key = (
                        str(
                            target[
                                "product_id"
                            ]
                        )
                        +
                        "|"
                        +
                        target[
                            "origin_date"
                        ].isoformat()
                    )

                    adjustments_by_model[
                        model_name
                    ][
                        key
                    ] = adjustment

    for target in targets:

        key = (
            str(
                target[
                    "product_id"
                ]
            )
            +
            "|"
            +
            target[
                "origin_date"
            ].isoformat()
        )

        eligible_global = [
            float(
                event[
                    "actual_return"
                ]
            )
            for event
            in matured
            if event[
                "product_id"
            ]
            !=
            target[
                "product_id"
            ]
        ]

        global_median = (
            statistics.median(
                eligible_global
            )
            if eligible_global
            else None
        )

        candidate_returns: dict[
            str,
            float | None
        ] = {
            "LAST_VALUE":
                0.0,

            "GLOBAL_REALIZED_MEDIAN":
                global_median,

            "EXACT_PEER_TRAJECTORY":
                (
                    None
                    if target[
                        "peer_trajectory"
                    ]
                    is None
                    else float(
                        target[
                            "peer_trajectory"
                        ]
                    )
                ),
        }

        for model_name in MULTIVARIATE_MODELS:

            adjustment = adjustments_by_model[
                model_name
            ].get(
                key
            )

            peer = target[
                "peer_trajectory"
            ]

            if (
                adjustment is None
                or
                peer is None
            ):

                candidate_returns[
                    model_name
                ] = None

            else:

                candidate_returns[
                    model_name
                ] = (
                    float(
                        peer
                    )
                    +
                    float(
                        adjustment
                    )
                )

        candidate_prices: dict[
            str,
            float | None
        ] = {}

        all_valid = True

        for model_name in ALL_MODELS:

            predicted_return = candidate_returns[
                model_name
            ]

            if (
                predicted_return is None
                or
                not math.isfinite(
                    float(
                        predicted_return
                    )
                )
            ):

                all_valid = False

                candidate_prices[
                    model_name
                ] = None

                continue

            predicted_price = safe_price(
                float(
                    target[
                        "origin_price"
                    ]
                ),
                float(
                    predicted_return
                ),
                int(
                    target[
                        "realized_days"
                    ]
                ),
            )

            if predicted_price is None:
                all_valid = False

            candidate_prices[
                model_name
            ] = predicted_price

        predictions.append(
            {
                "row":
                    target,

                "candidate_returns":
                    candidate_returns,

                "candidate_prices":
                    candidate_prices,

                "common":
                    all_valid,

                "parameter_counts":
                    parameter_counts,
            }
        )


common = [
    item
    for item
    in predictions
    if item[
        "common"
    ]
]


if not common:
    fail(
        "no common OOS folds across multivariate tournament"
    )


# ---------------------------------------------------------------------------
# Score same common folds for every candidate.
# ---------------------------------------------------------------------------

actual_returns = [
    float(
        item[
            "row"
        ][
            "actual_return"
        ]
    )
    for item
    in common
]


actual_prices = [
    float(
        item[
            "row"
        ][
            "endpoint_price"
        ]
    )
    for item
    in common
]


score_rows: list[
    dict[str, object]
] = []


for model_name in ALL_MODELS:

    predicted_returns = [
        float(
            item[
                "candidate_returns"
            ][
                model_name
            ]
        )
        for item
        in common
    ]

    predicted_prices = [
        float(
            item[
                "candidate_prices"
            ][
                model_name
            ]
        )
        for item
        in common
    ]

    model_smape = statistics.fmean(
        [
            smape(
                actual,
                predicted,
            )
            for actual, predicted
            in zip(
                actual_prices,
                predicted_prices,
            )
        ]
    )

    mae_usd = statistics.fmean(
        [
            abs(
                actual
                -
                predicted
            )
            for actual, predicted
            in zip(
                actual_prices,
                predicted_prices,
            )
        ]
    )

    log_return_mae = statistics.fmean(
        [
            abs(
                actual
                -
                predicted
            )
            for actual, predicted
            in zip(
                actual_returns,
                predicted_returns,
            )
        ]
    )

    log_return_bias = statistics.fmean(
        [
            predicted
            -
            actual
            for actual, predicted
            in zip(
                actual_returns,
                predicted_returns,
            )
        ]
    )

    rho = spearman(
        predicted_returns,
        actual_returns,
    )

    top_bottom = quartile_spread(
        predicted_returns,
        actual_returns,
    )

    unique_predictions = len(
        {
            f"{value:.12f}"
            for value
            in predicted_returns
        }
    )

    prediction_std = (
        statistics.pstdev(
            predicted_returns
        )
        if len(
            predicted_returns
        )
        >=
        2
        else
        0.0
    )

    score_rows.append(
        {
            "model_name":
                model_name,

            "model_class":
                (
                    "BENCHMARK"
                    if model_name
                    in BASELINES
                    else
                    "MULTIVARIATE_PRODUCT_SPECIFIC"
                ),

            "common_fold_rows":
                len(
                    common
                ),

            "smape":
                model_smape,

            "mae_usd":
                mae_usd,

            "log_return_mae":
                log_return_mae,

            "log_return_bias":
                log_return_bias,

            "spearman_rank_correlation":
                (
                    ""
                    if rho is None
                    else
                    rho
                ),

            "predicted_top_minus_bottom_quartile_realized_log_return":
                (
                    ""
                    if top_bottom is None
                    else
                    top_bottom
                ),

            "unique_predictions_12dp":
                unique_predictions,

            "prediction_standard_deviation":
                prediction_std,

            "positive_rank_discrimination":
                (
                    rho is not None
                    and
                    rho > 0
                ),

            "positive_top_bottom_spread":
                (
                    top_bottom is not None
                    and
                    top_bottom > 0
                ),

            "noncollapsed_prediction_distribution":
                (
                    unique_predictions > 1
                    and
                    prediction_std > 0
                ),

            "beats_exact_peer_smape":
                False,

            "promotion_eligible":
                False,
        }
    )


scores = {
    str(
        row[
            "model_name"
        ]
    ):
        row
    for row
    in score_rows
}


exact_peer_smape = float(
    scores[
        "EXACT_PEER_TRAJECTORY"
    ][
        "smape"
    ]
)


eligible: list[
    dict[str, object]
] = []


for score in score_rows:

    if score[
        "model_name"
    ] not in MULTIVARIATE_MODELS:
        continue

    beats_peer = (
        float(
            score[
                "smape"
            ]
        )
        <
        exact_peer_smape
    )

    score[
        "beats_exact_peer_smape"
    ] = beats_peer

    passes = (
        beats_peer
        and
        bool(
            score[
                "positive_rank_discrimination"
            ]
        )
        and
        bool(
            score[
                "positive_top_bottom_spread"
            ]
        )
        and
        bool(
            score[
                "noncollapsed_prediction_distribution"
            ]
        )
    )

    score[
        "promotion_eligible"
    ] = passes

    if passes:
        eligible.append(
            score
        )


if eligible:

    winner = sorted(
        eligible,
        key=lambda row: (
            float(
                row[
                    "smape"
                ]
            ),
            float(
                row[
                    "log_return_mae"
                ]
            ),
            -
            float(
                row[
                    "spearman_rank_correlation"
                ]
            ),
            str(
                row[
                    "model_name"
                ]
            ),
        ),
    )[0]

    winner_name = str(
        winner[
            "model_name"
        ]
    )

    promotion_status = (
        "MULTIVARIATE_PRODUCT_SPECIFIC_MODEL_PASSED_ACCURACY_AND_DISCRIMINATION_GATE"
    )

    next_gate = (
        "SL8D_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_PRODUCTION_FORECAST"
    )

else:

    winner_name = "NONE"

    promotion_status = (
        "NO_MULTIVARIATE_MODEL_PASSED_ACCURACY_AND_DISCRIMINATION_GATE"
    )

    next_gate = (
        "SL8C3_SECRET_LAIR_V1_1_MODEL_STRATEGY_REVIEW"
    )


# ---------------------------------------------------------------------------
# OOS prediction audit ledger.
# ---------------------------------------------------------------------------

prediction_ledger: list[
    dict[str, object]
] = []


for item in common:

    row = item[
        "row"
    ]

    ledger_row: dict[
        str,
        object
    ] = {
        "secret_lair_id":
            row[
                "product_id"
            ],

        "product_name":
            row[
                "product_name"
            ],

        "origin_date":
            row[
                "origin_date"
            ].isoformat(),

        "endpoint_date":
            row[
                "endpoint_date"
            ].isoformat(),

        "origin_price_usd":
            row[
                "origin_price"
            ],

        "actual_endpoint_price_usd":
            row[
                "endpoint_price"
            ],

        "actual_annualized_log_return":
            row[
                "actual_return"
            ],
    }

    for model_name in ALL_MODELS:

        ledger_row[
            model_name
            +
            "__PREDICTED_LOG_RETURN"
        ] = item[
            "candidate_returns"
        ][
            model_name
        ]

        ledger_row[
            model_name
            +
            "__PREDICTED_PRICE"
        ] = item[
            "candidate_prices"
        ][
            model_name
        ]

    prediction_ledger.append(
        ledger_row
    )


scoreboard_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_multivariate_product_model_tournament.csv"
)

predictions_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_multivariate_oos_predictions.csv"
)

summary_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_multivariate_product_model_tournament_summary.json"
)


write_csv(
    scoreboard_path,
    score_rows,
    [
        "model_name",
        "model_class",
        "common_fold_rows",
        "smape",
        "mae_usd",
        "log_return_mae",
        "log_return_bias",
        "spearman_rank_correlation",
        "predicted_top_minus_bottom_quartile_realized_log_return",
        "unique_predictions_12dp",
        "prediction_standard_deviation",
        "positive_rank_discrimination",
        "positive_top_bottom_spread",
        "noncollapsed_prediction_distribution",
        "beats_exact_peer_smape",
        "promotion_eligible",
    ],
)


write_csv(
    predictions_path,
    prediction_ledger,
    list(
        prediction_ledger[
            0
        ].keys()
    ),
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_MULTIVARIATE_PRODUCT_MODEL_TOURNAMENT_COMPLETE",

    "matrix_rows":
        len(
            rows
        ),

    "common_fold_rows":
        len(
            common
        ),

    "benchmark_models":
        list(
            BASELINES
        ),

    "multivariate_models":
        list(
            MULTIVARIATE_MODELS
        ),

    "architecture": {
        "anchor":
            "EXACT_PEER_TRAJECTORY",

        "learned_target":
            "REALIZED_ANNUALIZED_LOG_RETURN_MINUS_EXACT_PEER_TRAJECTORY",

        "estimator":
            "EXPANDING_WINDOW_ORDINARY_LEAST_SQUARES",

        "manual_feature_weights":
            False,

        "manual_relative_valuation_coefficient":
            False,

        "numeric_imputation":
            "TRAINING_WINDOW_MEDIAN_WITH_MISSING_INDICATOR",

        "numeric_standardization":
            "TRAINING_WINDOW_MEAN_AND_POPULATION_STANDARD_DEVIATION",

        "categorical_encoding":
            "TRAINING_WINDOW_REFERENCE_ONE_HOT",

        "current_snapshot_training":
            False,
    },

    "selection": {
        "exact_peer_common_fold_smape":
            exact_peer_smape,

        "promotion_candidate":
            winner_name,

        "promotion_status":
            promotion_status,

        "must_beat_exact_peer_smape":
            True,

        "positive_rank_discrimination_required":
            True,

        "positive_top_bottom_spread_required":
            True,

        "noncollapsed_distribution_required":
            True,

        "weighted_selection_score":
            False,

        "accuracy_alone_sufficient":
            False,
    },

    "governance": {
        "temporal_OOS":
            True,

        "common_fold_comparison":
            True,

        "only_matured_outcomes_enter_training":
            True,

        "future_information_in_features":
            False,

        "production_forecast_created":
            False,

        "V1_replaced":
            False,

        "ranking_changed":
            False,

        "purchase_recommendation_changed":
            False,

        "eBay_used":
            False,

        "automatic_purchase_execution":
            False,
    },

    "next_gate":
        next_gate,
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_V1_1_MULTIVARIATE_TOURNAMENT=PASS"
)

print(
    "COMMON_FOLD_ROWS="
    + str(
        len(
            common
        )
    )
)


for score in score_rows:

    print(
        "MODEL="
        + str(
            score[
                "model_name"
            ]
        )
        + "|SMAPE="
        + str(
            score[
                "smape"
            ]
        )
        + "|SPEARMAN="
        + str(
            score[
                "spearman_rank_correlation"
            ]
        )
        + "|TOP_BOTTOM="
        + str(
            score[
                "predicted_top_minus_bottom_quartile_realized_log_return"
            ]
        )
        + "|UNIQUE="
        + str(
            score[
                "unique_predictions_12dp"
            ]
        )
        + "|BEATS_PEER="
        + str(
            score[
                "beats_exact_peer_smape"
            ]
        ).upper()
        + "|PROMOTION="
        + str(
            score[
                "promotion_eligible"
            ]
        ).upper()
    )


print(
    "PROMOTION_CANDIDATE="
    + winner_name
)

print(
    "PROMOTION_STATUS="
    + promotion_status
)

print(
    "MANUAL_FEATURE_WEIGHTS_USED=FALSE"
)

print(
    "PRODUCTION_FORECAST_CREATED=FALSE"
)

print(
    "V1_REPLACED=FALSE"
)

print(
    "NEXT_GATE="
    + next_gate
)