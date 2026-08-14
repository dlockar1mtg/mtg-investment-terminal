from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np


DAYS_PER_YEAR = 365.0


MODELS = (
    "GLOBAL_REALIZED_MEDIAN",
    "GLOBAL_PLUS_MOMENTUM_OLS",
    "GLOBAL_PLUS_MOMENTUM_AND_PEER_GAP_OLS",
)


CANDIDATES = (
    "GLOBAL_PLUS_MOMENTUM_OLS",
    "GLOBAL_PLUS_MOMENTUM_AND_PEER_GAP_OLS",
)


MODEL_FIELDS = {
    "GLOBAL_PLUS_MOMENTUM_OLS": (
        "own_latest_interval_annualized_log_return",
        "own_recent_minus_median_momentum",
    ),

    "GLOBAL_PLUS_MOMENTUM_AND_PEER_GAP_OLS": (
        "own_latest_interval_annualized_log_return",
        "own_recent_minus_median_momentum",
        "peer_gap",
    ),
}


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

        result = (
            origin_price
            *
            math.exp(
                annualized_log_return
                *
                (
                    days
                    /
                    DAYS_PER_YEAR
                )
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
        enumerate(values),
        key=lambda item:
            item[1],
    )

    result = [
        0.0
        for _
        in values
    ]

    start = 0

    while start < len(indexed):

        end = start + 1

        while (
            end < len(indexed)
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

            result[
                indexed[
                    position
                ][0]
            ] = average

        start = end

    return result


def pearson(
    x: list[float],
    y: list[float],
) -> float | None:

    if len(x) != len(y):
        fail(
            "correlation input mismatch"
        )

    if len(x) < 2:
        return None

    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)

    numerator = sum(
        (
            a - mean_x
        )
        *
        (
            b - mean_y
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
                a - mean_x
            ) ** 2
            for a
            in x
        )
    )

    denominator_y = math.sqrt(
        sum(
            (
                b - mean_y
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

    return numerator / denominator


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
            "quartile input mismatch"
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

    size = (
        len(pairs)
        //
        4
    )

    if size < 1:
        return None

    bottom = [
        item[1]
        for item
        in pairs[:size]
    ]

    top = [
        item[1]
        for item
        in pairs[-size:]
    ]

    return (
        statistics.fmean(top)
        -
        statistics.fmean(bottom)
    )


def training_median(
    values: list[float | None],
) -> float:

    present = [
        float(value)
        for value
        in values
        if value is not None
    ]

    if not present:
        return 0.0

    return statistics.median(
        present
    )


def build_design(
    train_rows: list[dict[str, object]],
    prediction_rows: list[dict[str, object]],
    fields: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray]:

    if (
        not train_rows
        or
        not prediction_rows
    ):
        return (
            np.empty(
                (
                    len(train_rows),
                    0,
                )
            ),
            np.empty(
                (
                    len(prediction_rows),
                    0,
                )
            ),
        )

    train_columns: list[list[float]] = []
    prediction_columns: list[list[float]] = []

    for field in fields:

        raw_train = [
            row.get(field)
            for row
            in train_rows
        ]

        raw_prediction = [
            row.get(field)
            for row
            in prediction_rows
        ]

        median = training_median(
            raw_train
        )

        train_values = [
            (
                median
                if value is None
                else float(value)
            )
            for value
            in raw_train
        ]

        prediction_values = [
            (
                median
                if value is None
                else float(value)
            )
            for value
            in raw_prediction
        ]

        mean = statistics.fmean(
            train_values
        )

        std = (
            statistics.pstdev(
                train_values
            )
            if len(train_values) >= 2
            else 0.0
        )

        if std > 0:

            train_standardized = [
                (
                    value - mean
                )
                /
                std
                for value
                in train_values
            ]

            prediction_standardized = [
                (
                    value - mean
                )
                /
                std
                for value
                in prediction_values
            ]

        else:

            train_standardized = [
                0.0
                for _
                in train_values
            ]

            prediction_standardized = [
                0.0
                for _
                in prediction_values
            ]

        train_columns.append(
            train_standardized
        )

        prediction_columns.append(
            prediction_standardized
        )

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

    return (
        np.asarray(
            train_columns,
            dtype=float,
        ).T,

        np.asarray(
            prediction_columns,
            dtype=float,
        ).T,
    )


def fit_residual_model(
    train_rows: list[dict[str, object]],
    prediction_rows: list[dict[str, object]],
    model_name: str,
) -> list[float] | None:

    if (
        not train_rows
        or
        not prediction_rows
    ):
        return None

    fields = MODEL_FIELDS[
        model_name
    ]

    x_train, x_prediction = build_design(
        train_rows,
        prediction_rows,
        fields,
    )

    x_train = np.column_stack(
        (
            np.ones(
                len(train_rows)
            ),
            x_train,
        )
    )

    x_prediction = np.column_stack(
        (
            np.ones(
                len(prediction_rows)
            ),
            x_prediction,
        )
    )

    parameter_count = x_train.shape[1]

    # Identifiability support rule only.
    #
    # The number of matured training examples must exceed the number of fitted
    # parameters. This is not a performance threshold.
    if len(train_rows) <= parameter_count:
        return None

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
                    "historical_global_baseline"
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
        return None

    adjustments = (
        x_prediction
        @
        coefficients
    )

    result = [
        float(value)
        for value
        in adjustments
    ]

    if not all(
        math.isfinite(value)
        for value
        in result
    ):
        return None

    return result


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


source = read_csv(
    Path(
        args.matrix
    )
)

if len(source) != args.expected_rows:

    fail(
        "temporal matrix row drift: "
        f"expected={args.expected_rows}, "
        f"actual={len(source)}"
    )


# ---------------------------------------------------------------------------
# 1. Parse governed temporal rows.
# ---------------------------------------------------------------------------

rows: list[
    dict[str, object]
] = []


for raw in source:

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

    if (
        origin_price is None
        or origin_price <= 0
        or endpoint_price is None
        or endpoint_price <= 0
        or actual_return is None
    ):
        fail(
            "invalid governed target row"
        )

    rows.append(
        {
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

            "latest_momentum":
                as_float(
                    raw.get(
                        "own_latest_interval_annualized_log_return"
                    )
                ),

            "recent_minus_median":
                as_float(
                    raw.get(
                        "own_recent_minus_median_momentum"
                    )
                ),

            "peer_trajectory":
                as_float(
                    raw.get(
                        "exact_peer_median_annualized_log_return"
                    )
                ),
        }
    )


if not rows:
    fail(
        "parsed temporal matrix empty"
    )


# ---------------------------------------------------------------------------
# 2. Calculate each historical event's own leakage-safe global baseline.
#
# For a target at origin T:
#
#   GLOBAL_REALIZED_MEDIAN(T)
#
# uses only historical target outcomes whose endpoint date <= T and excludes
# the target product.
#
# This baseline is permanently associated with that historical event and is
# later used as its training residual anchor.
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


matured_by_origin: dict[
    date,
    list[dict[str, object]]
] = {}


for origin_date in origin_dates:

    matured_by_origin[
        origin_date
    ] = [
        row
        for row
        in rows
        if row[
            "endpoint_date"
        ]
        <=
        origin_date
    ]


for row in rows:

    matured = matured_by_origin[
        row[
            "origin_date"
        ]
    ]

    eligible = [
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
        row[
            "product_id"
        ]
    ]

    row[
        "historical_global_baseline"
    ] = (
        statistics.median(
            eligible
        )
        if eligible
        else None
    )

    peer = row[
        "peer_trajectory"
    ]

    baseline = row[
        "historical_global_baseline"
    ]

    if (
        peer is not None
        and
        baseline is not None
    ):

        row[
            "peer_gap"
        ] = (
            float(peer)
            -
            float(baseline)
        )

    else:

        row[
            "peer_gap"
        ] = None


# ---------------------------------------------------------------------------
# 3. Expanding-window OOS predictions.
# ---------------------------------------------------------------------------

prediction_records: list[
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
        if (
            row[
                "endpoint_date"
            ]
            <=
            origin_date
            and
            row[
                "historical_global_baseline"
            ]
            is not None
        )
    ]

    prediction_targets = [
        row
        for row
        in targets
        if row[
            "historical_global_baseline"
        ]
        is not None
    ]

    adjustments: dict[
        str,
        dict[str, float]
    ] = {
        model:
            {}
        for model
        in CANDIDATES
    }

    for model in CANDIDATES:

        fitted = fit_residual_model(
            matured,
            prediction_targets,
            model,
        )

        if fitted is None:
            continue

        for target, adjustment in zip(
            prediction_targets,
            fitted,
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

            adjustments[
                model
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

        global_baseline = target[
            "historical_global_baseline"
        ]

        predictions: dict[
            str,
            float | None
        ] = {
            "GLOBAL_REALIZED_MEDIAN":
                (
                    None
                    if global_baseline is None
                    else float(
                        global_baseline
                    )
                )
        }

        for model in CANDIDATES:

            adjustment = adjustments[
                model
            ].get(
                key
            )

            if (
                global_baseline is None
                or
                adjustment is None
            ):

                predictions[
                    model
                ] = None

            else:

                predictions[
                    model
                ] = (
                    float(
                        global_baseline
                    )
                    +
                    float(
                        adjustment
                    )
                )

        prices: dict[
            str,
            float | None
        ] = {}

        common = True

        for model in MODELS:

            prediction = predictions[
                model
            ]

            if (
                prediction is None
                or
                not math.isfinite(
                    float(
                        prediction
                    )
                )
            ):

                common = False
                prices[
                    model
                ] = None

                continue

            predicted_price = safe_price(
                float(
                    target[
                        "origin_price"
                    ]
                ),
                float(
                    prediction
                ),
                int(
                    target[
                        "realized_days"
                    ]
                ),
            )

            if predicted_price is None:
                common = False

            prices[
                model
            ] = predicted_price

        prediction_records.append(
            {
                "row":
                    target,

                "predictions":
                    predictions,

                "prices":
                    prices,

                "common":
                    common,
            }
        )


common = [
    item
    for item
    in prediction_records
    if item[
        "common"
    ]
]


if not common:
    fail(
        "no common OOS folds across SL-8C.5 candidates"
    )


# ---------------------------------------------------------------------------
# 4. Event-level common-fold tournament.
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


event_scores: list[
    dict[str, object]
] = []


for model in MODELS:

    predicted_returns = [
        float(
            item[
                "predictions"
            ][
                model
            ]
        )
        for item
        in common
    ]

    predicted_prices = [
        float(
            item[
                "prices"
            ][
                model
            ]
        )
        for item
        in common
    ]

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

    dispersion = (
        statistics.pstdev(
            predicted_returns
        )
        if len(predicted_returns) >= 2
        else 0.0
    )

    event_scores.append(
        {
            "model_name":
                model,

            "model_class":
                (
                    "CALIBRATION_BASELINE"
                    if model
                    ==
                    "GLOBAL_REALIZED_MEDIAN"
                    else
                    "PRODUCT_SPECIFIC_CANDIDATE"
                ),

            "common_fold_rows":
                len(common),

            "smape":
                statistics.fmean(
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
                ),

            "log_return_mae":
                statistics.fmean(
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
                ),

            "spearman_rank_correlation":
                (
                    ""
                    if rho is None
                    else rho
                ),

            "top_minus_bottom_quartile_realized_log_return":
                (
                    ""
                    if top_bottom is None
                    else top_bottom
                ),

            "unique_predictions_12dp":
                unique_predictions,

            "prediction_dispersion":
                dispersion,

            "beats_global_common_fold_smape":
                False,

            "positive_discrimination":
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
                    dispersion > 0
                ),

            "event_gate_passed":
                False,
        }
    )


event_by_model = {
    str(
        row[
            "model_name"
        ]
    ):
        row
    for row
    in event_scores
}


global_event_smape = float(
    event_by_model[
        "GLOBAL_REALIZED_MEDIAN"
    ][
        "smape"
    ]
)


for model in CANDIDATES:

    score = event_by_model[
        model
    ]

    beats = (
        float(
            score[
                "smape"
            ]
        )
        <
        global_event_smape
    )

    score[
        "beats_global_common_fold_smape"
    ] = beats

    score[
        "event_gate_passed"
    ] = (
        beats
        and
        bool(
            score[
                "positive_discrimination"
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


# ---------------------------------------------------------------------------
# 5. Equal-product robustness on the EXACT SAME common folds.
# ---------------------------------------------------------------------------

events_by_product: dict[
    str,
    list[dict[str, object]]
] = defaultdict(list)


for item in common:

    product_id = str(
        item[
            "row"
        ][
            "product_id"
        ]
    )

    events_by_product[
        product_id
    ].append(
        item
    )


product_rows: list[
    dict[str, object]
] = []


for product_id in sorted(
    events_by_product
):

    events = events_by_product[
        product_id
    ]

    summary_row: dict[
        str,
        object
    ] = {
        "product_id":
            product_id,

        "event_count":
            len(events),

        "mean_actual_return":
            statistics.fmean(
                [
                    float(
                        item[
                            "row"
                        ][
                            "actual_return"
                        ]
                    )
                    for item
                    in events
                ]
            ),
    }

    for model in MODELS:

        summary_row[
            model
            +
            "__MEAN_PREDICTED_RETURN"
        ] = statistics.fmean(
            [
                float(
                    item[
                        "predictions"
                    ][
                        model
                    ]
                )
                for item
                in events
            ]
        )

        summary_row[
            model
            +
            "__MEAN_SMAPE"
        ] = statistics.fmean(
            [
                smape(
                    float(
                        item[
                            "row"
                        ][
                            "endpoint_price"
                        ]
                    ),
                    float(
                        item[
                            "prices"
                        ][
                            model
                        ]
                    ),
                )
                for item
                in events
            ]
        )

        summary_row[
            model
            +
            "__MEAN_RETURN_MAE"
        ] = statistics.fmean(
            [
                abs(
                    float(
                        item[
                            "row"
                        ][
                            "actual_return"
                        ]
                    )
                    -
                    float(
                        item[
                            "predictions"
                        ][
                            model
                        ]
                    )
                )
                for item
                in events
            ]
        )

    product_rows.append(
        summary_row
    )


actual_product_returns = [
    float(
        row[
            "mean_actual_return"
        ]
    )
    for row
    in product_rows
]


product_scores: list[
    dict[str, object]
] = []


for model in MODELS:

    predicted_product_returns = [
        float(
            row[
                model
                +
                "__MEAN_PREDICTED_RETURN"
            ]
        )
        for row
        in product_rows
    ]

    rho = spearman(
        predicted_product_returns,
        actual_product_returns,
    )

    top_bottom = quartile_spread(
        predicted_product_returns,
        actual_product_returns,
    )

    unique_predictions = len(
        {
            f"{value:.12f}"
            for value
            in predicted_product_returns
        }
    )

    dispersion = (
        statistics.pstdev(
            predicted_product_returns
        )
        if len(
            predicted_product_returns
        )
        >=
        2
        else
        0.0
    )

    product_scores.append(
        {
            "model_name":
                model,

            "model_class":
                (
                    "CALIBRATION_BASELINE"
                    if model
                    ==
                    "GLOBAL_REALIZED_MEDIAN"
                    else
                    "PRODUCT_SPECIFIC_CANDIDATE"
                ),

            "product_count":
                len(
                    product_rows
                ),

            "event_count":
                len(
                    common
                ),

            "product_balanced_smape":
                statistics.fmean(
                    [
                        float(
                            row[
                                model
                                +
                                "__MEAN_SMAPE"
                            ]
                        )
                        for row
                        in product_rows
                    ]
                ),

            "product_balanced_log_return_mae":
                statistics.fmean(
                    [
                        float(
                            row[
                                model
                                +
                                "__MEAN_RETURN_MAE"
                            ]
                        )
                        for row
                        in product_rows
                    ]
                ),

            "product_level_spearman":
                (
                    ""
                    if rho is None
                    else rho
                ),

            "product_top_minus_bottom_quartile_realized_log_return":
                (
                    ""
                    if top_bottom is None
                    else top_bottom
                ),

            "unique_product_mean_predictions_12dp":
                unique_predictions,

            "product_prediction_dispersion":
                dispersion,

            "beats_global_product_balanced_smape":
                False,

            "positive_product_discrimination":
                (
                    rho is not None
                    and
                    rho > 0
                ),

            "positive_product_top_bottom_spread":
                (
                    top_bottom is not None
                    and
                    top_bottom > 0
                ),

            "noncollapsed_product_prediction_distribution":
                (
                    unique_predictions > 1
                    and
                    dispersion > 0
                ),

            "product_gate_passed":
                False,
        }
    )


product_by_model = {
    str(
        row[
            "model_name"
        ]
    ):
        row
    for row
    in product_scores
}


global_product_smape = float(
    product_by_model[
        "GLOBAL_REALIZED_MEDIAN"
    ][
        "product_balanced_smape"
    ]
)


for model in CANDIDATES:

    score = product_by_model[
        model
    ]

    beats = (
        float(
            score[
                "product_balanced_smape"
            ]
        )
        <
        global_product_smape
    )

    score[
        "beats_global_product_balanced_smape"
    ] = beats

    score[
        "product_gate_passed"
    ] = (
        beats
        and
        bool(
            score[
                "positive_product_discrimination"
            ]
        )
        and
        bool(
            score[
                "positive_product_top_bottom_spread"
            ]
        )
        and
        bool(
            score[
                "noncollapsed_product_prediction_distribution"
            ]
        )
    )


# ---------------------------------------------------------------------------
# 6. Final promotion.
#
# No weighted score.
#
# Candidate must independently pass BOTH gates.
# ---------------------------------------------------------------------------

eligible: list[
    str
] = []


for model in CANDIDATES:

    if (
        bool(
            event_by_model[
                model
            ][
                "event_gate_passed"
            ]
        )
        and
        bool(
            product_by_model[
                model
            ][
                "product_gate_passed"
            ]
        )
    ):

        eligible.append(
            model
        )


if eligible:

    winner = sorted(
        eligible,
        key=lambda model: (
            float(
                event_by_model[
                    model
                ][
                    "smape"
                ]
            ),
            float(
                product_by_model[
                    model
                ][
                    "product_balanced_smape"
                ]
            ),
            -
            float(
                product_by_model[
                    model
                ][
                    "product_level_spearman"
                ]
            ),
            model,
        ),
    )[0]

    promotion_status = (
        "GLOBAL_CALIBRATED_PRODUCT_SPECIFIC_MODEL_PASSED_TEMPORAL_AND_PRODUCT_BALANCED_GATES"
    )

    next_gate = (
        "SL8D_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_PRODUCTION_FORECAST"
    )

else:

    winner = "NONE"

    promotion_status = (
        "NO_GLOBAL_CALIBRATED_PRODUCT_SPECIFIC_MODEL_PASSED_BOTH_GATES"
    )

    next_gate = (
        "SL8C6_SECRET_LAIR_V1_1_MODELING_STOP_AND_SIGNAL_PLACEMENT_REVIEW"
    )


# ---------------------------------------------------------------------------
# 7. Prediction ledger.
# ---------------------------------------------------------------------------

ledger: list[
    dict[str, object]
] = []


for item in common:

    source_row = item[
        "row"
    ]

    ledger_row: dict[
        str,
        object
    ] = {
        "secret_lair_id":
            source_row[
                "product_id"
            ],

        "product_name":
            source_row[
                "product_name"
            ],

        "origin_date":
            source_row[
                "origin_date"
            ].isoformat(),

        "endpoint_date":
            source_row[
                "endpoint_date"
            ].isoformat(),

        "origin_price_usd":
            source_row[
                "origin_price"
            ],

        "actual_endpoint_price_usd":
            source_row[
                "endpoint_price"
            ],

        "actual_annualized_log_return":
            source_row[
                "actual_return"
            ],

        "historical_global_baseline":
            source_row[
                "historical_global_baseline"
            ],

        "latest_momentum":
            source_row[
                "latest_momentum"
            ],

        "recent_minus_median_momentum":
            source_row[
                "recent_minus_median"
            ],

        "exact_peer_trajectory":
            source_row[
                "peer_trajectory"
            ],

        "exact_peer_minus_global_baseline":
            source_row[
                "peer_gap"
            ],
    }

    for model in MODELS:

        ledger_row[
            model
            +
            "__PREDICTED_LOG_RETURN"
        ] = item[
            "predictions"
        ][
            model
        ]

        ledger_row[
            model
            +
            "__PREDICTED_PRICE"
        ] = item[
            "prices"
        ][
            model
        ]

    ledger.append(
        ledger_row
    )


run_root = Path(
    args.run_root
)


event_path = (
    run_root
    /
    "secret_lair_v1_1_global_calibrated_event_tournament.csv"
)

product_path = (
    run_root
    /
    "secret_lair_v1_1_global_calibrated_product_balanced_tournament.csv"
)

prediction_path = (
    run_root
    /
    "secret_lair_v1_1_global_calibrated_oos_predictions.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_1_global_calibrated_product_model_tournament_summary.json"
)


write_csv(
    event_path,
    event_scores,
    [
        "model_name",
        "model_class",
        "common_fold_rows",
        "smape",
        "log_return_mae",
        "spearman_rank_correlation",
        "top_minus_bottom_quartile_realized_log_return",
        "unique_predictions_12dp",
        "prediction_dispersion",
        "beats_global_common_fold_smape",
        "positive_discrimination",
        "positive_top_bottom_spread",
        "noncollapsed_prediction_distribution",
        "event_gate_passed",
    ],
)


write_csv(
    product_path,
    product_scores,
    [
        "model_name",
        "model_class",
        "product_count",
        "event_count",
        "product_balanced_smape",
        "product_balanced_log_return_mae",
        "product_level_spearman",
        "product_top_minus_bottom_quartile_realized_log_return",
        "unique_product_mean_predictions_12dp",
        "product_prediction_dispersion",
        "beats_global_product_balanced_smape",
        "positive_product_discrimination",
        "positive_product_top_bottom_spread",
        "noncollapsed_product_prediction_distribution",
        "product_gate_passed",
    ],
)


write_csv(
    prediction_path,
    ledger,
    list(
        ledger[
            0
        ].keys()
    ),
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_GLOBAL_CALIBRATED_PRODUCT_MODEL_TOURNAMENT_COMPLETE",

    "source_matrix_rows":
        len(rows),

    "common_fold_rows":
        len(common),

    "product_balanced_products":
        len(product_rows),

    "models":
        list(MODELS),

    "architecture": {
        "base_return":
            "GLOBAL_REALIZED_MEDIAN_AVAILABLE_AT_EACH_HISTORICAL_ORIGIN",

        "training_residual_target":
            "REALIZED_RETURN_MINUS_EVENT_SPECIFIC_HISTORICAL_GLOBAL_BASELINE",

        "estimator":
            "EXPANDING_WINDOW_ORDINARY_LEAST_SQUARES",

        "manual_feature_weights":
            False,

        "manual_blend_weight":
            False,

        "only_matured_targets_enter_training":
            True,

        "event_specific_training_baseline_reconstructed_at_original_origin":
            True,

        "current_snapshot_used_for_historical_training":
            False,
    },

    "event_gate": {
        "global_baseline_smape":
            global_event_smape,

        "must_beat_global_smape":
            True,

        "positive_rank_discrimination_required":
            True,

        "positive_top_bottom_spread_required":
            True,

        "noncollapsed_distribution_required":
            True,
    },

    "product_gate": {
        "global_product_balanced_smape":
            global_product_smape,

        "equal_product_weighting":
            True,

        "must_beat_global_product_balanced_smape":
            True,

        "positive_product_discrimination_required":
            True,

        "positive_product_top_bottom_spread_required":
            True,

        "noncollapsed_product_distribution_required":
            True,
    },

    "selection": {
        "promotion_candidate":
            winner,

        "promotion_status":
            promotion_status,

        "weighted_selection_score":
            False,

        "both_event_and_product_gates_required":
            True,
    },

    "governance": {
        "temporal_OOS":
            True,

        "product_balanced_confirmation":
            True,

        "model_fitted_for_tournament":
            True,

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
    "SECRET_LAIR_V1_1_GLOBAL_CALIBRATED_TOURNAMENT=PASS"
)

print(
    "COMMON_FOLD_ROWS="
    + str(
        len(common)
    )
)

print(
    "PRODUCT_BALANCED_PRODUCTS="
    + str(
        len(product_rows)
    )
)


for row in event_scores:

    print(
        "EVENT_MODEL="
        + str(
            row[
                "model_name"
            ]
        )
        + "|SMAPE="
        + str(
            row[
                "smape"
            ]
        )
        + "|SPEARMAN="
        + str(
            row[
                "spearman_rank_correlation"
            ]
        )
        + "|TOP_BOTTOM="
        + str(
            row[
                "top_minus_bottom_quartile_realized_log_return"
            ]
        )
        + "|UNIQUE="
        + str(
            row[
                "unique_predictions_12dp"
            ]
        )
        + "|GATE="
        + str(
            row[
                "event_gate_passed"
            ]
        ).upper()
    )


for row in product_scores:

    print(
        "PRODUCT_MODEL="
        + str(
            row[
                "model_name"
            ]
        )
        + "|PB_SMAPE="
        + str(
            row[
                "product_balanced_smape"
            ]
        )
        + "|PB_SPEARMAN="
        + str(
            row[
                "product_level_spearman"
            ]
        )
        + "|PB_TOP_BOTTOM="
        + str(
            row[
                "product_top_minus_bottom_quartile_realized_log_return"
            ]
        )
        + "|UNIQUE_PRODUCTS="
        + str(
            row[
                "unique_product_mean_predictions_12dp"
            ]
        )
        + "|GATE="
        + str(
            row[
                "product_gate_passed"
            ]
        ).upper()
    )


print(
    "PROMOTION_CANDIDATE="
    + winner
)

print(
    "PROMOTION_STATUS="
    + promotion_status
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