from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from collections import defaultdict
from pathlib import Path


MODELS = (
    "LAST_VALUE",
    "GLOBAL_REALIZED_MEDIAN",
    "EXACT_PEER_TRAJECTORY",
    "ANCHOR_PLUS_MOMENTUM_OLS",
)

BASELINES = (
    "LAST_VALUE",
    "GLOBAL_REALIZED_MEDIAN",
    "EXACT_PEER_TRAJECTORY",
)

CANDIDATE = "ANCHOR_PLUS_MOMENTUM_OLS"


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def finite_float(value: object) -> float:
    text = clean(value)

    if not text:
        fail(
            "blank required numeric value"
        )

    result = float(text)

    if not math.isfinite(result):
        fail(
            "non-finite required numeric value"
        )

    return result


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
    x: list[float],
    y: list[float],
) -> float | None:

    return pearson(
        average_ranks(x),
        average_ranks(y),
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
        value[1]
        for value
        in pairs[:size]
    ]

    top = [
        value[1]
        for value
        in pairs[-size:]
    ]

    return (
        statistics.fmean(top)
        -
        statistics.fmean(bottom)
    )


parser = argparse.ArgumentParser()

parser.add_argument(
    "--predictions",
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


raw_rows = read_csv(
    Path(
        args.predictions
    )
)

if len(raw_rows) != args.expected_rows:
    fail(
        "OOS ledger row drift: "
        f"expected={args.expected_rows}, "
        f"actual={len(raw_rows)}"
    )


product_rows: dict[
    str,
    list[dict[str, object]],
] = defaultdict(list)


for raw in raw_rows:

    product_id = clean(
        raw.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank product identity"
        )

    parsed: dict[str, object] = {
        "product_id":
            product_id,

        "actual_return":
            finite_float(
                raw.get(
                    "actual_annualized_log_return"
                )
            ),

        "actual_price":
            finite_float(
                raw.get(
                    "actual_endpoint_price_usd"
                )
            ),
    }

    for model in MODELS:

        parsed[
            model
            +
            "__RETURN"
        ] = finite_float(
            raw.get(
                model
                +
                "__PREDICTED_LOG_RETURN"
            )
        )

        parsed[
            model
            +
            "__PRICE"
        ] = finite_float(
            raw.get(
                model
                +
                "__PREDICTED_PRICE"
            )
        )

    product_rows[
        product_id
    ].append(
        parsed
    )


if not product_rows:
    fail(
        "no products in OOS ledger"
    )


# ---------------------------------------------------------------------------
# Product-level summaries.
#
# Every Secret Lair contributes exactly one product-level observation to the
# robustness aggregation regardless of historical event count.
# ---------------------------------------------------------------------------

product_level: list[
    dict[str, object]
] = []


for product_id in sorted(
    product_rows
):

    events = product_rows[
        product_id
    ]

    row: dict[str, object] = {
        "product_id":
            product_id,

        "event_count":
            len(events),

        "mean_actual_return":
            statistics.fmean(
                [
                    float(
                        event[
                            "actual_return"
                        ]
                    )
                    for event
                    in events
                ]
            ),
    }

    for model in MODELS:

        model_return_key = (
            model
            +
            "__RETURN"
        )

        model_price_key = (
            model
            +
            "__PRICE"
        )

        product_smapes = [
            smape(
                float(
                    event[
                        "actual_price"
                    ]
                ),
                float(
                    event[
                        model_price_key
                    ]
                ),
            )
            for event
            in events
        ]

        product_return_errors = [
            abs(
                float(
                    event[
                        "actual_return"
                    ]
                )
                -
                float(
                    event[
                        model_return_key
                    ]
                )
            )
            for event
            in events
        ]

        row[
            model
            +
            "__MEAN_SMAPE"
        ] = statistics.fmean(
            product_smapes
        )

        row[
            model
            +
            "__MEAN_RETURN_MAE"
        ] = statistics.fmean(
            product_return_errors
        )

        row[
            model
            +
            "__MEAN_PREDICTED_RETURN"
        ] = statistics.fmean(
            [
                float(
                    event[
                        model_return_key
                    ]
                )
                for event
                in events
            ]
        )

    product_level.append(
        row
    )


# ---------------------------------------------------------------------------
# Equal-product aggregate tournament.
# ---------------------------------------------------------------------------

score_rows: list[
    dict[str, object]
] = []


actual_product_returns = [
    float(
        row[
            "mean_actual_return"
        ]
    )
    for row
    in product_level
]


for model in MODELS:

    product_smapes = [
        float(
            row[
                model
                +
                "__MEAN_SMAPE"
            ]
        )
        for row
        in product_level
    ]

    product_return_maes = [
        float(
            row[
                model
                +
                "__MEAN_RETURN_MAE"
            ]
        )
        for row
        in product_level
    ]

    predicted_product_returns = [
        float(
            row[
                model
                +
                "__MEAN_PREDICTED_RETURN"
            ]
        )
        for row
        in product_level
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

    score_rows.append(
        {
            "model_name":
                model,

            "model_class":
                (
                    "BASELINE"
                    if model
                    in BASELINES
                    else
                    "PRODUCT_SPECIFIC_CANDIDATE"
                ),

            "product_count":
                len(
                    product_level
                ),

            "event_count":
                len(
                    raw_rows
                ),

            "product_balanced_smape":
                statistics.fmean(
                    product_smapes
                ),

            "product_balanced_log_return_mae":
                statistics.fmean(
                    product_return_maes
                ),

            "product_level_spearman":
                (
                    ""
                    if rho is None
                    else
                    rho
                ),

            "product_top_minus_bottom_quartile_realized_log_return":
                (
                    ""
                    if top_bottom is None
                    else
                    top_bottom
                ),

            "unique_product_mean_predictions_12dp":
                unique_predictions,

            "product_prediction_dispersion":
                dispersion,

            "beats_best_product_balanced_baseline_smape":
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

            "production_robustness_confirmed":
                False,
        }
    )


score_by_model = {
    str(
        row[
            "model_name"
        ]
    ):
        row
    for row
    in score_rows
}


best_baseline_smape = min(
    float(
        score_by_model[
            model
        ][
            "product_balanced_smape"
        ]
    )
    for model
    in BASELINES
)


candidate = score_by_model[
    CANDIDATE
]


beats_best_baseline = (
    float(
        candidate[
            "product_balanced_smape"
        ]
    )
    <
    best_baseline_smape
)


candidate[
    "beats_best_product_balanced_baseline_smape"
] = beats_best_baseline


production_confirmed = (
    beats_best_baseline
    and
    bool(
        candidate[
            "positive_product_discrimination"
        ]
    )
    and
    bool(
        candidate[
            "positive_product_top_bottom_spread"
        ]
    )
)


candidate[
    "production_robustness_confirmed"
] = production_confirmed


if production_confirmed:

    status = (
        "MULTIVARIATE_PRODUCT_SPECIFIC_MODEL_CONFIRMED_BY_PRODUCT_BALANCED_ROBUSTNESS"
    )

    next_gate = (
        "SL8D_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_PRODUCTION_FORECAST"
    )

else:

    status = (
        "MULTIVARIATE_PRODUCT_SPECIFIC_MODEL_NOT_CONFIRMED_BY_PRODUCT_BALANCED_ROBUSTNESS"
    )

    next_gate = (
        "SL8C4_SECRET_LAIR_V1_1_MODEL_STRATEGY_REVIEW"
    )


scoreboard_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_product_balanced_robustness.csv"
)

summary_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_product_balanced_robustness_summary.json"
)


write_csv(
    scoreboard_path,
    score_rows,
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
        "beats_best_product_balanced_baseline_smape",
        "positive_product_discrimination",
        "positive_product_top_bottom_spread",
        "production_robustness_confirmed",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_PRODUCT_BALANCED_ROBUSTNESS_COMPLETE",

    "products":
        len(
            product_level
        ),

    "events":
        len(
            raw_rows
        ),

    "candidate":
        CANDIDATE,

    "best_product_balanced_baseline_smape":
        best_baseline_smape,

    "candidate_product_balanced_smape":
        candidate[
            "product_balanced_smape"
        ],

    "candidate_product_level_spearman":
        candidate[
            "product_level_spearman"
        ],

    "candidate_product_top_bottom_spread":
        candidate[
            "product_top_minus_bottom_quartile_realized_log_return"
        ],

    "candidate_unique_product_mean_predictions":
        candidate[
            "unique_product_mean_predictions_12dp"
        ],

    "production_robustness_confirmed":
        production_confirmed,

    "result_status":
        status,

    "governance": {
        "model_refitted":
            False,

        "new_predictions_generated":
            False,

        "equal_product_weighting":
            True,

        "weighted_selection_score":
            False,

        "must_beat_best_product_balanced_baseline_smape":
            True,

        "positive_product_discrimination_required":
            True,

        "positive_product_top_bottom_spread_required":
            True,

        "production_forecast_created":
            False,

        "V1_replaced":
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
    "SECRET_LAIR_V1_1_PRODUCT_BALANCED_ROBUSTNESS=PASS"
)

print(
    "PRODUCTS="
    + str(
        len(
            product_level
        )
    )
)

print(
    "EVENTS="
    + str(
        len(
            raw_rows
        )
    )
)


for row in score_rows:

    print(
        "MODEL="
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
        + "|ROBUSTNESS="
        + str(
            row[
                "production_robustness_confirmed"
            ]
        ).upper()
    )


print(
    "PRODUCTION_ROBUSTNESS_CONFIRMED="
    + str(
        production_confirmed
    ).upper()
)

print(
    "RESULT_STATUS="
    + status
)

print(
    "MODEL_REFITTED=FALSE"
)

print(
    "PRODUCTION_FORECAST_CREATED=FALSE"
)

print(
    "NEXT_GATE="
    + next_gate
)