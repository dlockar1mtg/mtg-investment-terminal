from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from datetime import date
from pathlib import Path


MODELS = (
    "LAST_VALUE",
    "GLOBAL_REALIZED_MEDIAN",
    "OWN_ANNUALIZED_TRAJECTORY",
    "OWN_LOG_PRICE_SLOPE",
    "RECENT_MOMENTUM",
    "EXACT_PEER_TRAJECTORY",
)

BASELINES = (
    "LAST_VALUE",
    "GLOBAL_REALIZED_MEDIAN",
)

PRODUCT_SPECIFIC = (
    "OWN_ANNUALIZED_TRAJECTORY",
    "OWN_LOG_PRICE_SLOPE",
    "RECENT_MOMENTUM",
    "EXACT_PEER_TRAJECTORY",
)

DAYS_PER_YEAR = 365.0


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def as_float(value: object) -> float | None:
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


def as_date(value: object) -> date:
    return date.fromisoformat(
        clean(value)[:10]
    )


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


def median_or_none(
    values: list[float],
) -> float | None:

    if not values:
        return None

    return statistics.median(
        values
    )


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
        or result <= 0
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
        key=lambda pair:
            pair[1],
    )

    ranks = [
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

        rank = (
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
            original = indexed[
                position
            ][0]

            ranks[
                original
            ] = rank

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

    group_size = (
        len(pairs)
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
        statistics.fmean(top)
        -
        statistics.fmean(bottom)
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


rows = read_csv(
    Path(
        args.matrix
    )
)

if len(rows) != args.expected_rows:
    fail(
        "temporal matrix row drift: "
        f"expected={args.expected_rows}, "
        f"actual={len(rows)}"
    )


parsed: list[
    dict[str, object]
] = []


for row in rows:

    origin_price = as_float(
        row.get(
            "origin_price_usd"
        )
    )

    endpoint_price = as_float(
        row.get(
            "target_endpoint_price_usd"
        )
    )

    actual_return = as_float(
        row.get(
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
            "invalid target row"
        )

    realized_days = int(
        clean(
            row.get(
                "target_realized_days"
            )
        )
    )

    parsed.append(
        {
            "product_id":
                clean(
                    row.get(
                        "secret_lair_id"
                    )
                ),

            "origin_date":
                as_date(
                    row.get(
                        "origin_date"
                    )
                ),

            "endpoint_date":
                as_date(
                    row.get(
                        "target_endpoint_date"
                    )
                ),

            "origin_price":
                origin_price,

            "endpoint_price":
                endpoint_price,

            "realized_days":
                realized_days,

            "actual_return":
                actual_return,

            "own_trajectory":
                as_float(
                    row.get(
                        "own_full_history_annualized_log_return"
                    )
                ),

            "own_slope":
                as_float(
                    row.get(
                        "own_log_price_slope_annualized"
                    )
                ),

            "recent_momentum":
                as_float(
                    row.get(
                        "own_latest_interval_annualized_log_return"
                    )
                ),

            "peer_trajectory":
                as_float(
                    row.get(
                        "exact_peer_median_annualized_log_return"
                    )
                ),

            "peer_log_valuation":
                as_float(
                    row.get(
                        "current_vs_exact_peer_median_log_valuation"
                    )
                ),
        }
    )


origin_dates = sorted(
    {
        row[
            "origin_date"
        ]
        for row
        in parsed
    }
)


matured_by_origin: dict[
    date,
    list[dict[str, object]],
] = {}


for origin_date in origin_dates:

    matured_by_origin[
        origin_date
    ] = [
        row
        for row
        in parsed
        if row[
            "endpoint_date"
        ]
        <=
        origin_date
    ]


prediction_rows: list[
    dict[str, object]
] = []


for row in parsed:

    target_product = row[
        "product_id"
    ]

    matured = matured_by_origin[
        row[
            "origin_date"
        ]
    ]

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
        target_product
    ]

    global_median = median_or_none(
        eligible_global
    )

    candidate_returns = {
        "LAST_VALUE":
            0.0,

        "GLOBAL_REALIZED_MEDIAN":
            global_median,

        "OWN_ANNUALIZED_TRAJECTORY":
            row[
                "own_trajectory"
            ],

        "OWN_LOG_PRICE_SLOPE":
            row[
                "own_slope"
            ],

        "RECENT_MOMENTUM":
            row[
                "recent_momentum"
            ],

        "EXACT_PEER_TRAJECTORY":
            row[
                "peer_trajectory"
            ],
    }

    candidate_prices: dict[
        str,
        float | None
    ] = {}

    all_valid = True

    for model_name in MODELS:

        prediction = candidate_returns[
            model_name
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
            all_valid = False
            candidate_prices[
                model_name
            ] = None

            continue

        predicted_price = safe_price(
            float(
                row[
                    "origin_price"
                ]
            ),
            float(
                prediction
            ),
            int(
                row[
                    "realized_days"
                ]
            ),
        )

        if predicted_price is None:
            all_valid = False

        candidate_prices[
            model_name
        ] = predicted_price

    prediction_rows.append(
        {
            "row":
                row,

            "candidate_returns":
                candidate_returns,

            "candidate_prices":
                candidate_prices,

            "common":
                all_valid,
        }
    )


common = [
    item
    for item
    in prediction_rows
    if item[
        "common"
    ]
]


if not common:
    fail(
        "no common folds"
    )


score_rows: list[
    dict[str, object]
] = []


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


for model_name in MODELS:

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

    bias = statistics.fmean(
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

    prediction_std = statistics.pstdev(
        predicted_returns
    )

    score_rows.append(
        {
            "model_name":
                model_name,

            "model_class":
                (
                    "V1_STYLE_BASELINE"
                    if model_name
                    in BASELINES
                    else
                    "PRODUCT_SPECIFIC_CANDIDATE"
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
                bias,

            "spearman_rank_correlation":
                (
                    ""
                    if rho is None
                    else rho
                ),

            "predicted_top_minus_bottom_quartile_realized_log_return":
                (
                    ""
                    if top_bottom is None
                    else top_bottom
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

            "beats_best_baseline_smape":
                False,

            "promotion_eligible":
                False,
        }
    )


score_by_model = {
    row[
        "model_name"
    ]:
        row
    for row
    in score_rows
}


best_baseline_smape = min(
    float(
        score_by_model[
            model_name
        ][
            "smape"
        ]
    )
    for model_name
    in BASELINES
)


eligible: list[
    dict[str, object]
] = []


for score in score_rows:

    if score[
        "model_name"
    ] not in PRODUCT_SPECIFIC:
        continue

    beats = (
        float(
            score[
                "smape"
            ]
        )
        <
        best_baseline_smape
    )

    score[
        "beats_best_baseline_smape"
    ] = beats

    passes = (
        bool(
            score[
                "noncollapsed_prediction_distribution"
            ]
        )
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
        beats
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

    promotion_candidate = str(
        winner[
            "model_name"
        ]
    )

    promotion_status = (
        "SIMPLE_PRODUCT_SPECIFIC_CANDIDATE_PASSED_GATE"
    )

    next_gate = (
        "SL8D_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_PRODUCTION_FORECAST"
    )

else:

    promotion_candidate = "NONE"

    promotion_status = (
        "NO_SIMPLE_PRODUCT_SPECIFIC_CANDIDATE_PASSED_GATE"
    )

    next_gate = (
        "SL8C2_SECRET_LAIR_V1_1_MULTIVARIATE_PRODUCT_MODEL_TOURNAMENT"
    )


# ---------------------------------------------------------------------------
# Relative valuation diagnostic.
#
# It is NOT converted into forecast return using an arbitrary coefficient.
# Negative valuation signal means cheaper versus exact structural peers.
# ---------------------------------------------------------------------------

valuation_predicted: list[float] = []
valuation_actual: list[float] = []


for item in common:

    valuation = item[
        "row"
    ][
        "peer_log_valuation"
    ]

    if (
        isinstance(
            valuation,
            (
                int,
                float,
            )
        )
        and
        math.isfinite(
            float(
                valuation
            )
        )
    ):
        valuation_predicted.append(
            -
            float(
                valuation
            )
        )

        valuation_actual.append(
            float(
                item[
                    "row"
                ][
                    "actual_return"
                ]
            )
        )


valuation_rho = spearman(
    valuation_predicted,
    valuation_actual,
) if valuation_predicted else None


valuation_top_bottom = quartile_spread(
    valuation_predicted,
    valuation_actual,
) if valuation_predicted else None


scoreboard_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_product_signal_tournament.csv"
)

summary_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_product_signal_tournament_summary.json"
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
        "beats_best_baseline_smape",
        "promotion_eligible",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_PRODUCT_SIGNAL_TOURNAMENT_COMPLETE",

    "matrix_rows":
        len(
            parsed
        ),

    "common_fold_rows":
        len(
            common
        ),

    "models":
        list(
            MODELS
        ),

    "baseline_models":
        list(
            BASELINES
        ),

    "product_specific_candidates":
        list(
            PRODUCT_SPECIFIC
        ),

    "relative_valuation_diagnostic": {
        "rows":
            len(
                valuation_predicted
            ),

        "signal":
            "NEGATIVE_CURRENT_VS_EXACT_PEER_MEDIAN_LOG_VALUATION",

        "arbitrary_forecast_coefficient_used":
            False,

        "spearman_rank_correlation":
            valuation_rho,

        "top_minus_bottom_quartile_realized_log_return":
            valuation_top_bottom,
    },

    "selection": {
        "best_baseline_smape":
            best_baseline_smape,

        "promotion_candidate":
            promotion_candidate,

        "promotion_status":
            promotion_status,

        "weighted_score_used":
            False,

        "accuracy_alone_sufficient":
            False,

        "positive_rank_discrimination_required":
            True,

        "positive_top_bottom_spread_required":
            True,

        "noncollapsed_distribution_required":
            True,

        "must_beat_best_baseline_smape":
            True,
    },

    "governance": {
        "temporal_OOS":
            True,

        "common_fold_comparison":
            True,

        "historical_target_may_train_only_after_endpoint_date":
            True,

        "global_baseline_target_product_holdout":
            True,

        "current_snapshot_used_for_training":
            False,

        "arbitrary_relative_valuation_coefficient_used":
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
    "SECRET_LAIR_V1_1_PRODUCT_SIGNAL_TOURNAMENT=PASS"
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
        + "|PROMOTION="
        + str(
            score[
                "promotion_eligible"
            ]
        ).upper()
    )


print(
    "RELATIVE_VALUATION_ROWS="
    + str(
        len(
            valuation_predicted
        )
    )
)

print(
    "RELATIVE_VALUATION_SPEARMAN="
    + str(
        valuation_rho
    )
)

print(
    "RELATIVE_VALUATION_TOP_BOTTOM="
    + str(
        valuation_top_bottom
    )
)

print(
    "ARBITRARY_RELATIVE_VALUATION_COEFFICIENT_USED=FALSE"
)

print(
    "PROMOTION_CANDIDATE="
    + promotion_candidate
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