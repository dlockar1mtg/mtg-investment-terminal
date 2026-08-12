from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from collections import defaultdict
from pathlib import Path


SIGNALS = (
    "LATEST_INTERVAL_MOMENTUM",
    "RECENT_MINUS_MEDIAN_MOMENTUM",
)


SOURCE_FIELDS = {
    "LATEST_INTERVAL_MOMENTUM":
        "own_latest_interval_annualized_log_return",

    "RECENT_MINUS_MEDIAN_MOMENTUM":
        "own_recent_minus_median_momentum",
}


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


def average_ranks(values: list[float]) -> list[float]:

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

        average_rank = (
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

            ranks[
                indexed[
                    position
                ][0]
            ] = average_rank

        start = end

    return ranks


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
                value - mean_x
            ) ** 2
            for value
            in x
        )
    )

    denominator_y = math.sqrt(
        sum(
            (
                value - mean_y
            ) ** 2
            for value
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
    signal: list[float],
    actual: list[float],
) -> float | None:

    return pearson(
        average_ranks(signal),
        average_ranks(actual),
    )


def quartile_spread(
    signal: list[float],
    actual: list[float],
) -> float | None:

    if len(signal) != len(actual):
        fail(
            "quartile input mismatch"
        )

    if len(signal) < 4:
        return None

    pairs = sorted(
        zip(
            signal,
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


raw_rows = read_csv(
    Path(
        args.matrix
    )
)

if len(raw_rows) != args.expected_rows:

    fail(
        "temporal matrix row drift: "
        f"expected={args.expected_rows}, "
        f"actual={len(raw_rows)}"
    )


# ---------------------------------------------------------------------------
# Use exactly the population where BOTH candidate ranking signals exist.
#
# This preserves a common evaluation population across the two signals.
# ---------------------------------------------------------------------------

rows: list[dict[str, object]] = []


for raw in raw_rows:

    product_id = clean(
        raw.get(
            "secret_lair_id"
        )
    )

    actual_return = as_float(
        raw.get(
            "target_realized_annualized_log_return"
        )
    )

    latest = as_float(
        raw.get(
            SOURCE_FIELDS[
                "LATEST_INTERVAL_MOMENTUM"
            ]
        )
    )

    recent_minus = as_float(
        raw.get(
            SOURCE_FIELDS[
                "RECENT_MINUS_MEDIAN_MOMENTUM"
            ]
        )
    )

    if (
        not product_id
        or
        actual_return is None
        or
        latest is None
        or
        recent_minus is None
    ):
        continue

    rows.append(
        {
            "product_id":
                product_id,

            "actual_return":
                actual_return,

            "LATEST_INTERVAL_MOMENTUM":
                latest,

            "RECENT_MINUS_MEDIAN_MOMENTUM":
                recent_minus,
        }
    )


if not rows:
    fail(
        "no common signal-evaluation rows"
    )


# ---------------------------------------------------------------------------
# Event-level diagnostics.
# ---------------------------------------------------------------------------

event_actual = [
    float(
        row[
            "actual_return"
        ]
    )
    for row
    in rows
]


# ---------------------------------------------------------------------------
# Product-balanced diagnostics.
#
# Each product receives exactly one influence by averaging its historical
# signal values and realized outcomes.
# ---------------------------------------------------------------------------

by_product: dict[
    str,
    list[dict[str, object]]
] = defaultdict(list)


for row in rows:

    by_product[
        str(
            row[
                "product_id"
            ]
        )
    ].append(
        row
    )


product_rows: list[
    dict[str, object]
] = []


for product_id in sorted(
    by_product
):

    events = by_product[
        product_id
    ]

    product_rows.append(
        {
            "product_id":
                product_id,

            "event_count":
                len(events),

            "actual_return":
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

            "LATEST_INTERVAL_MOMENTUM":
                statistics.fmean(
                    [
                        float(
                            event[
                                "LATEST_INTERVAL_MOMENTUM"
                            ]
                        )
                        for event
                        in events
                    ]
                ),

            "RECENT_MINUS_MEDIAN_MOMENTUM":
                statistics.fmean(
                    [
                        float(
                            event[
                                "RECENT_MINUS_MEDIAN_MOMENTUM"
                            ]
                        )
                        for event
                        in events
                    ]
                ),
        }
    )


product_actual = [
    float(
        row[
            "actual_return"
        ]
    )
    for row
    in product_rows
]


score_rows: list[
    dict[str, object]
] = []


for signal in SIGNALS:

    event_values = [
        float(
            row[
                signal
            ]
        )
        for row
        in rows
    ]

    product_values = [
        float(
            row[
                signal
            ]
        )
        for row
        in product_rows
    ]

    event_rho = spearman(
        event_values,
        event_actual,
    )

    event_spread = quartile_spread(
        event_values,
        event_actual,
    )

    product_rho = spearman(
        product_values,
        product_actual,
    )

    product_spread = quartile_spread(
        product_values,
        product_actual,
    )

    event_positive = (
        event_rho is not None
        and
        event_rho > 0
        and
        event_spread is not None
        and
        event_spread > 0
    )

    product_positive = (
        product_rho is not None
        and
        product_rho > 0
        and
        product_spread is not None
        and
        product_spread > 0
    )

    placement_supported = (
        event_positive
        and
        product_positive
    )

    score_rows.append(
        {
            "signal_name":
                signal,

            "common_event_rows":
                len(rows),

            "product_count":
                len(product_rows),

            "event_spearman":
                (
                    ""
                    if event_rho is None
                    else event_rho
                ),

            "event_top_minus_bottom_realized_log_return":
                (
                    ""
                    if event_spread is None
                    else event_spread
                ),

            "product_balanced_spearman":
                (
                    ""
                    if product_rho is None
                    else product_rho
                ),

            "product_balanced_top_minus_bottom_realized_log_return":
                (
                    ""
                    if product_spread is None
                    else product_spread
                ),

            "event_discrimination_positive":
                event_positive,

            "product_discrimination_positive":
                product_positive,

            "ranking_signal_placement_supported":
                placement_supported,
        }
    )


supported = [
    str(
        row[
            "signal_name"
        ]
    )
    for row
    in score_rows
    if bool(
        row[
            "ranking_signal_placement_supported"
        ]
    )
]


if supported:

    result_status = (
        "PRODUCT_SPECIFIC_SIGNAL_SUPPORTED_FOR_DOWNSTREAM_RANKING_EVALUATION"
    )

    next_gate = (
        "SL8D_SECRET_LAIR_V1_1_RANKING_SIGNAL_INTEGRATION"
    )

else:

    result_status = (
        "NO_PRODUCT_SPECIFIC_SIGNAL_SUPPORTED_FOR_PRODUCTION_PLACEMENT"
    )

    next_gate = (
        "SL8D_SECRET_LAIR_V1_1_ENHANCEMENT_CLOSEOUT_WITH_V1_AUTHORITY"
    )


scoreboard_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_signal_placement_review.csv"
)

summary_path = (
    Path(
        args.run_root
    )
    /
    "secret_lair_v1_1_signal_placement_review_summary.json"
)


write_csv(
    scoreboard_path,
    score_rows,
    [
        "signal_name",
        "common_event_rows",
        "product_count",
        "event_spearman",
        "event_top_minus_bottom_realized_log_return",
        "product_balanced_spearman",
        "product_balanced_top_minus_bottom_realized_log_return",
        "event_discrimination_positive",
        "product_discrimination_positive",
        "ranking_signal_placement_supported",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_MODELING_STOP_AND_SIGNAL_PLACEMENT_REVIEW_COMPLETE",

    "point_forecast_modeling": {
        "additional_experimentation_authorized":
            False,

        "V1_1_point_forecast_promoted":
            False,

        "certified_V1_forecast_authority_preserved":
            True,

        "reason":
            "NO_PRODUCT_SPECIFIC_POINT_FORECAST_MODEL_PASSED_GOVERNED_TEMPORAL_AND_PRODUCT_BALANCED_PROMOTION_GATES",
    },

    "signal_review": {
        "common_event_rows":
            len(rows),

        "product_count":
            len(product_rows),

        "signals":
            list(SIGNALS),

        "supported_ranking_signals":
            supported,

        "model_fitted":
            False,

        "forecast_accuracy_metric_used_for_signal_placement":
            False,

        "event_positive_discrimination_required":
            True,

        "product_positive_discrimination_required":
            True,

        "manual_signal_weight_created":
            False,

        "production_ranking_created":
            False,
    },

    "result_status":
        result_status,

    "governance": {
        "point_forecast_experimentation_stopped":
            True,

        "V1_replaced":
            False,

        "production_forecast_created":
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
    "SECRET_LAIR_V1_1_SIGNAL_PLACEMENT_REVIEW=PASS"
)

print(
    "COMMON_EVENT_ROWS="
    + str(
        len(rows)
    )
)

print(
    "PRODUCTS="
    + str(
        len(product_rows)
    )
)


for row in score_rows:

    print(
        "SIGNAL="
        + str(
            row[
                "signal_name"
            ]
        )
        + "|EVENT_SPEARMAN="
        + str(
            row[
                "event_spearman"
            ]
        )
        + "|EVENT_TOP_BOTTOM="
        + str(
            row[
                "event_top_minus_bottom_realized_log_return"
            ]
        )
        + "|PRODUCT_SPEARMAN="
        + str(
            row[
                "product_balanced_spearman"
            ]
        )
        + "|PRODUCT_TOP_BOTTOM="
        + str(
            row[
                "product_balanced_top_minus_bottom_realized_log_return"
            ]
        )
        + "|PLACEMENT="
        + str(
            row[
                "ranking_signal_placement_supported"
            ]
        ).upper()
    )


print(
    "SUPPORTED_RANKING_SIGNALS="
    + (
        ",".join(supported)
        if supported
        else
        "NONE"
    )
)

print(
    "POINT_FORECAST_EXPERIMENTATION_STOPPED=TRUE"
)

print(
    "V1_1_POINT_FORECAST_PROMOTED=FALSE"
)

print(
    "V1_FORECAST_AUTHORITY_PRESERVED=TRUE"
)

print(
    "PRODUCTION_RANKING_CREATED=FALSE"
)

print(
    "RESULT_STATUS="
    + result_status
)

print(
    "NEXT_GATE="
    + next_gate
)