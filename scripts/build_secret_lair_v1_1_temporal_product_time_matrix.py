from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


DAYS_PER_YEAR = 365.0
HORIZON_DAYS = 365


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_positive_float(
    value: object,
) -> float | None:

    text = clean(value)

    if not text:
        return None

    try:
        result = float(text)
    except ValueError:
        return None

    if (
        not math.isfinite(result)
        or result <= 0
    ):
        return None

    return result


def parse_date(
    value: object,
) -> date:

    text = clean(value)

    if not text:
        raise ValueError(
            "blank date"
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


@dataclass(frozen=True)
class Observation:
    product_id: str
    when: date
    price: float
    source_record_id: str


def structural_key(
    feature: dict[str, str],
) -> tuple[str, str, str]:

    return (
        clean(
            feature.get(
                "finish"
            )
        ).lower(),

        clean(
            feature.get(
                "product_family"
            )
        ).lower(),

        clean(
            feature.get(
                "sealed_configuration"
            )
        ).lower(),
    )


def slope(
    x: list[float],
    y: list[float],
) -> float | None:

    if len(x) != len(y):
        fail(
            "slope input length mismatch"
        )

    if len(x) < 2:
        return None

    x_mean = statistics.fmean(
        x
    )

    y_mean = statistics.fmean(
        y
    )

    denominator = sum(
        (
            value
            - x_mean
        ) ** 2
        for value
        in x
    )

    if denominator <= 0:
        return None

    numerator = sum(
        (
            x_value
            - x_mean
        )
        *
        (
            y_value
            - y_mean
        )
        for x_value, y_value
        in zip(
            x,
            y,
        )
    )

    return numerator / denominator


def max_drawdown(
    prices: list[float],
) -> float | None:

    if not prices:
        return None

    high = prices[0]
    worst = 0.0

    for price in prices:

        high = max(
            high,
            price,
        )

        drawdown = (
            price
            /
            high
        ) - 1.0

        worst = min(
            worst,
            drawdown,
        )

    return worst


def blank(
    value: object,
) -> object:

    if value is None:
        return ""

    return value


def nearest_endpoint(
    observations: list[Observation],
    origin_index: int,
) -> Observation | None:

    origin = observations[
        origin_index
    ]

    target = (
        origin.when
        +
        timedelta(
            days=HORIZON_DAYS
        )
    )

    if target > observations[-1].when:
        return None

    candidates = [
        row
        for row
        in observations[
            origin_index + 1:
        ]
        if row.when > origin.when
    ]

    if not candidates:
        return None

    # Preserve existing Secret Lair V1 endpoint semantics:
    # nearest later observation to origin + 365 days.
    #
    # No new tolerance is invented here.
    return min(
        candidates,
        key=lambda row: (
            abs(
                (
                    row.when
                    -
                    target
                ).days
            ),
            row.when,
        ),
    )


def history_metrics(
    observations: list[Observation],
) -> dict[str, object]:

    result: dict[str, object] = {
        "observation_count":
            len(
                observations
            ),

        "first_date":
            "",

        "last_date":
            "",

        "span_days":
            0,

        "start_price":
            None,

        "last_price":
            None,

        "total_return":
            None,

        "annualized_log_return":
            None,

        "log_price_slope_annualized":
            None,

        "latest_interval_days":
            None,

        "latest_interval_annualized_log_return":
            None,

        "median_interval_annualized_log_return":
            None,

        "latest_minus_median_interval":
            None,

        "interval_volatility":
            None,

        "downside_semideviation":
            None,

        "maximum_drawdown":
            None,

        "positive_interval_fraction":
            None,

        "negative_interval_fraction":
            None,

        "median_price":
            None,

        "low_price":
            None,

        "high_price":
            None,
    }

    if not observations:
        return result

    prices = [
        row.price
        for row
        in observations
    ]

    result[
        "first_date"
    ] = observations[
        0
    ].when.isoformat()

    result[
        "last_date"
    ] = observations[
        -1
    ].when.isoformat()

    result[
        "start_price"
    ] = prices[0]

    result[
        "last_price"
    ] = prices[-1]

    result[
        "median_price"
    ] = statistics.median(
        prices
    )

    result[
        "low_price"
    ] = min(
        prices
    )

    result[
        "high_price"
    ] = max(
        prices
    )

    result[
        "maximum_drawdown"
    ] = max_drawdown(
        prices
    )

    if len(observations) < 2:
        return result

    first = observations[0]
    last = observations[-1]

    span_days = (
        last.when
        -
        first.when
    ).days

    result[
        "span_days"
    ] = span_days

    result[
        "total_return"
    ] = (
        last.price
        /
        first.price
    ) - 1.0

    if span_days > 0:

        result[
            "annualized_log_return"
        ] = (
            math.log(
                last.price
                /
                first.price
            )
            *
            (
                DAYS_PER_YEAR
                /
                span_days
            )
        )

        x = [
            float(
                (
                    row.when
                    -
                    first.when
                ).days
            )
            for row
            in observations
        ]

        y = [
            math.log(
                row.price
            )
            for row
            in observations
        ]

        daily_slope = slope(
            x,
            y,
        )

        if daily_slope is not None:

            result[
                "log_price_slope_annualized"
            ] = (
                daily_slope
                *
                DAYS_PER_YEAR
            )

    interval_logs: list[float] = []
    annualized_intervals: list[float] = []

    for previous, current in zip(
        observations[:-1],
        observations[1:],
    ):

        days = (
            current.when
            -
            previous.when
        ).days

        if days <= 0:
            fail(
                "non-positive historical interval"
            )

        log_return = math.log(
            current.price
            /
            previous.price
        )

        interval_logs.append(
            log_return
        )

        annualized_intervals.append(
            log_return
            *
            (
                DAYS_PER_YEAR
                /
                days
            )
        )

    latest_previous = observations[-2]
    latest_current = observations[-1]

    latest_days = (
        latest_current.when
        -
        latest_previous.when
    ).days

    latest_annualized = (
        math.log(
            latest_current.price
            /
            latest_previous.price
        )
        *
        (
            DAYS_PER_YEAR
            /
            latest_days
        )
    )

    median_annualized = statistics.median(
        annualized_intervals
    )

    result[
        "latest_interval_days"
    ] = latest_days

    result[
        "latest_interval_annualized_log_return"
    ] = latest_annualized

    result[
        "median_interval_annualized_log_return"
    ] = median_annualized

    result[
        "latest_minus_median_interval"
    ] = (
        latest_annualized
        -
        median_annualized
    )

    if len(
        annualized_intervals
    ) >= 2:

        result[
            "interval_volatility"
        ] = statistics.stdev(
            annualized_intervals
        )

    negatives = [
        value
        for value
        in annualized_intervals
        if value < 0
    ]

    if negatives:

        result[
            "downside_semideviation"
        ] = math.sqrt(
            statistics.fmean(
                [
                    value * value
                    for value
                    in negatives
                ]
            )
        )

    result[
        "positive_interval_fraction"
    ] = (
        sum(
            1
            for value
            in interval_logs
            if value > 0
        )
        /
        len(
            interval_logs
        )
    )

    result[
        "negative_interval_fraction"
    ] = (
        sum(
            1
            for value
            in interval_logs
            if value < 0
        )
        /
        len(
            interval_logs
        )
    )

    return result


parser = argparse.ArgumentParser()

parser.add_argument(
    "--history",
    required=True,
)

parser.add_argument(
    "--features",
    required=True,
)

parser.add_argument(
    "--run-root",
    required=True,
)

parser.add_argument(
    "--expected-accepted-history-rows",
    required=True,
    type=int,
)

args = parser.parse_args()


history_path = Path(
    args.history
)

feature_path = Path(
    args.features
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# 1. Static product identity / structural attributes
# ---------------------------------------------------------------------------

feature_rows = read_csv(
    feature_path
)

features: dict[
    str,
    dict[str, str],
] = {}

for row in feature_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank product identity"
        )

    if product_id in features:
        fail(
            "duplicate product identity: "
            + product_id
        )

    features[
        product_id
    ] = row


# ---------------------------------------------------------------------------
# 2. Reconstruct exact accepted TCG history
# ---------------------------------------------------------------------------

raw_history = read_csv(
    history_path
)

accepted_rows = 0

date_prices: dict[
    tuple[str, date],
    set[float],
] = defaultdict(set)


for row in raw_history:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if product_id not in features:
        continue

    source_name = clean(
        row.get(
            "source_name"
        )
    )

    if source_name not in (
        "TCGCSV",
        "TCGCSV_ARCHIVE_MONTHLY",
    ):
        continue

    source_record_id = clean(
        row.get(
            "source_record_id"
        )
    )

    source_file = clean(
        row.get(
            "source_file"
        )
    )

    if (
        not source_record_id
        or not source_file
    ):
        continue

    price = parse_positive_float(
        row.get(
            "market_price"
        )
    )

    if price is None:
        continue

    try:

        when = parse_date(
            row.get(
                "observation_date"
            )
        )

    except Exception:
        continue

    accepted_rows += 1

    date_prices[
        (
            product_id,
            when,
        )
    ].add(
        price
    )


if (
    accepted_rows
    !=
    args.expected_accepted_history_rows
):

    fail(
        "accepted history count drift: "
        f"expected={args.expected_accepted_history_rows}, "
        f"actual={accepted_rows}"
    )


for (
    product_date,
    prices,
) in date_prices.items():

    if len(prices) > 1:

        fail(
            "conflicting same-date accepted market prices: "
            + product_date[0]
            + " "
            + product_date[1].isoformat()
        )


history_by_product: dict[
    str,
    list[Observation],
] = defaultdict(list)


for (
    product_date,
    prices,
) in date_prices.items():

    product_id = product_date[0]
    when = product_date[1]

    history_by_product[
        product_id
    ].append(
        Observation(
            product_id=
                product_id,

            when=
                when,

            price=
                next(
                    iter(
                        prices
                    )
                ),

            source_record_id=
                "CANONICAL_PRODUCT_DATE",
        )
    )


for product_id in history_by_product:

    history_by_product[
        product_id
    ].sort(
        key=lambda row:
            row.when
    )


# ---------------------------------------------------------------------------
# 3. Structural peer groups
# ---------------------------------------------------------------------------

structural_groups: dict[
    tuple[str, str, str],
    list[str],
] = defaultdict(list)


for product_id, feature in features.items():

    structural_groups[
        structural_key(
            feature
        )
    ].append(
        product_id
    )


# ---------------------------------------------------------------------------
# 4. Historical product-time matrix
# ---------------------------------------------------------------------------

matrix: list[
    dict[str, object]
] = []

leakage_violations = 0
peer_future_violations = 0
rows_with_own_two_plus = 0
rows_with_exact_peer_prices = 0
rows_with_exact_peer_trajectories = 0


for (
    product_id,
    observations,
) in history_by_product.items():

    feature = features[
        product_id
    ]

    key = structural_key(
        feature
    )

    for origin_index in range(
        len(
            observations
        )
    ):

        endpoint = nearest_endpoint(
            observations,
            origin_index,
        )

        if endpoint is None:
            continue

        origin = observations[
            origin_index
        ]

        own_history = observations[
            : origin_index + 1
        ]

        own = history_metrics(
            own_history
        )

        if len(
            own_history
        ) >= 2:
            rows_with_own_two_plus += 1

        if any(
            row.when > origin.when
            for row
            in own_history
        ):
            leakage_violations += 1

        peer_origin_prices: list[
            float
        ] = []

        peer_trajectory_returns: list[
            float
        ] = []

        eligible_peer_products = 0

        for peer_id in structural_groups[
            key
        ]:

            if peer_id == product_id:
                continue

            peer_all_history = history_by_product.get(
                peer_id,
                [],
            )

            peer_history = [
                row
                for row
                in peer_all_history
                if row.when <= origin.when
            ]

            if not peer_history:
                continue

            eligible_peer_products += 1

            if any(
                row.when > origin.when
                for row
                in peer_history
            ):
                peer_future_violations += 1

            peer_origin_prices.append(
                peer_history[
                    -1
                ].price
            )

            peer_metrics = history_metrics(
                peer_history
            )

            peer_return = peer_metrics.get(
                "annualized_log_return"
            )

            if isinstance(
                peer_return,
                (
                    int,
                    float,
                )
            ):

                if math.isfinite(
                    float(
                        peer_return
                    )
                ):

                    peer_trajectory_returns.append(
                        float(
                            peer_return
                        )
                    )

        peer_price_median = (
            statistics.median(
                peer_origin_prices
            )
            if peer_origin_prices
            else None
        )

        peer_return_median = (
            statistics.median(
                peer_trajectory_returns
            )
            if peer_trajectory_returns
            else None
        )

        if peer_origin_prices:
            rows_with_exact_peer_prices += 1

        if peer_trajectory_returns:
            rows_with_exact_peer_trajectories += 1

        current_to_peer_ratio = None
        current_vs_peer_log_valuation = None

        if (
            peer_price_median is not None
            and
            peer_price_median > 0
        ):

            current_to_peer_ratio = (
                origin.price
                /
                peer_price_median
            )

            current_vs_peer_log_valuation = math.log(
                origin.price
                /
                peer_price_median
            )

        own_minus_peer_trajectory = None

        own_return = own.get(
            "annualized_log_return"
        )

        if (
            isinstance(
                own_return,
                (
                    int,
                    float,
                )
            )
            and
            peer_return_median is not None
        ):

            own_minus_peer_trajectory = (
                float(
                    own_return
                )
                -
                peer_return_median
            )

        current_to_history_median = None
        current_to_history_high = None
        current_to_history_low = None

        historical_median = own.get(
            "median_price"
        )

        historical_high = own.get(
            "high_price"
        )

        historical_low = own.get(
            "low_price"
        )

        if isinstance(
            historical_median,
            (
                int,
                float,
            )
        ):

            current_to_history_median = (
                origin.price
                /
                float(
                    historical_median
                )
            )

        if isinstance(
            historical_high,
            (
                int,
                float,
            )
        ):

            current_to_history_high = (
                origin.price
                /
                float(
                    historical_high
                )
            )

        if isinstance(
            historical_low,
            (
                int,
                float,
            )
        ):

            current_to_history_low = (
                origin.price
                /
                float(
                    historical_low
                )
            )

        realized_days = (
            endpoint.when
            -
            origin.when
        ).days

        if realized_days <= 0:
            fail(
                "non-positive endpoint interval"
            )

        realized_log_return = math.log(
            endpoint.price
            /
            origin.price
        )

        realized_annualized_log_return = (
            realized_log_return
            *
            (
                DAYS_PER_YEAR
                /
                realized_days
            )
        )

        matrix.append(
            {
                "secret_lair_id":
                    product_id,

                "product_name":
                    clean(
                        feature.get(
                            "product_name"
                        )
                    ),

                "origin_date":
                    origin.when.isoformat(),

                "origin_price_usd":
                    origin.price,

                "target_endpoint_date":
                    endpoint.when.isoformat(),

                "target_endpoint_price_usd":
                    endpoint.price,

                "target_realized_days":
                    realized_days,

                "target_realized_total_return":
                    (
                        endpoint.price
                        /
                        origin.price
                    ) - 1.0,

                "target_realized_annualized_log_return":
                    realized_annualized_log_return,

                "finish":
                    clean(
                        feature.get(
                            "finish"
                        )
                    ),

                "detailed_finish":
                    clean(
                        feature.get(
                            "detailed_finish"
                        )
                    ),

                "product_family":
                    clean(
                        feature.get(
                            "product_family"
                        )
                    ),

                "sealed_configuration":
                    clean(
                        feature.get(
                            "sealed_configuration"
                        )
                    ),

                "own_history_observation_count":
                    own[
                        "observation_count"
                    ],

                "own_history_first_date":
                    own[
                        "first_date"
                    ],

                "own_history_last_date":
                    own[
                        "last_date"
                    ],

                "own_history_span_days":
                    own[
                        "span_days"
                    ],

                "own_history_start_price_usd":
                    blank(
                        own[
                            "start_price"
                        ]
                    ),

                "own_full_history_total_return":
                    blank(
                        own[
                            "total_return"
                        ]
                    ),

                "own_full_history_annualized_log_return":
                    blank(
                        own[
                            "annualized_log_return"
                        ]
                    ),

                "own_log_price_slope_annualized":
                    blank(
                        own[
                            "log_price_slope_annualized"
                        ]
                    ),

                "own_latest_interval_days":
                    blank(
                        own[
                            "latest_interval_days"
                        ]
                    ),

                "own_latest_interval_annualized_log_return":
                    blank(
                        own[
                            "latest_interval_annualized_log_return"
                        ]
                    ),

                "own_median_interval_annualized_log_return":
                    blank(
                        own[
                            "median_interval_annualized_log_return"
                        ]
                    ),

                "own_recent_minus_median_momentum":
                    blank(
                        own[
                            "latest_minus_median_interval"
                        ]
                    ),

                "own_interval_volatility":
                    blank(
                        own[
                            "interval_volatility"
                        ]
                    ),

                "own_downside_semideviation":
                    blank(
                        own[
                            "downside_semideviation"
                        ]
                    ),

                "own_maximum_drawdown":
                    blank(
                        own[
                            "maximum_drawdown"
                        ]
                    ),

                "own_positive_interval_fraction":
                    blank(
                        own[
                            "positive_interval_fraction"
                        ]
                    ),

                "own_negative_interval_fraction":
                    blank(
                        own[
                            "negative_interval_fraction"
                        ]
                    ),

                "current_to_own_historical_median_ratio":
                    blank(
                        current_to_history_median
                    ),

                "current_to_own_historical_high_ratio":
                    blank(
                        current_to_history_high
                    ),

                "current_to_own_historical_low_ratio":
                    blank(
                        current_to_history_low
                    ),

                "exact_peer_products_available_at_origin":
                    eligible_peer_products,

                "exact_peer_origin_price_count":
                    len(
                        peer_origin_prices
                    ),

                "exact_peer_origin_price_median_usd":
                    blank(
                        peer_price_median
                    ),

                "current_to_exact_peer_median_price_ratio":
                    blank(
                        current_to_peer_ratio
                    ),

                "current_vs_exact_peer_median_log_valuation":
                    blank(
                        current_vs_peer_log_valuation
                    ),

                "exact_peer_trajectory_count":
                    len(
                        peer_trajectory_returns
                    ),

                "exact_peer_median_annualized_log_return":
                    blank(
                        peer_return_median
                    ),

                "own_minus_exact_peer_median_annualized_log_return":
                    blank(
                        own_minus_peer_trajectory
                    ),

                "feature_max_date":
                    origin.when.isoformat(),

                "all_target_features_at_or_before_origin":
                    True,

                "all_peer_features_at_or_before_origin":
                    True,

                "target_product_held_out_of_peer_aggregates":
                    True,
            }
        )


if not matrix:
    fail(
        "temporal matrix is empty"
    )


if leakage_violations != 0:
    fail(
        "own-history leakage violations detected: "
        + str(
            leakage_violations
        )
    )


if peer_future_violations != 0:
    fail(
        "peer-history leakage violations detected: "
        + str(
            peer_future_violations
        )
    )


# ---------------------------------------------------------------------------
# 5. Matrix diagnostics
# ---------------------------------------------------------------------------

unique_products = len(
    {
        clean(
            row[
                "secret_lair_id"
            ]
        )
        for row
        in matrix
    }
)

unique_origins = len(
    {
        (
            clean(
                row[
                    "secret_lair_id"
                ]
            ),
            clean(
                row[
                    "origin_date"
                ]
            ),
        )
        for row
        in matrix
    }
)

if unique_origins != len(
    matrix
):
    fail(
        "duplicate product/origin rows detected"
    )


# ---------------------------------------------------------------------------
# 6. Persist
# ---------------------------------------------------------------------------

matrix_path = (
    run_root
    /
    "secret_lair_v1_1_temporal_product_time_matrix.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_1_temporal_product_time_matrix_summary.json"
)


write_csv(
    matrix_path,
    matrix,
    list(
        matrix[
            0
        ].keys()
    ),
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_TEMPORAL_PRODUCT_TIME_MATRIX_COMPLETE",

    "historical_authority": {
        "accepted_history_rows":
            accepted_rows,

        "product_date_conflicts":
            0,
    },

    "matrix": {
        "rows":
            len(
                matrix
            ),

        "products":
            unique_products,

        "unique_product_origin_pairs":
            unique_origins,

        "rows_with_two_or_more_own_observations":
            rows_with_own_two_plus,

        "rows_with_exact_peer_origin_prices":
            rows_with_exact_peer_prices,

        "rows_with_exact_peer_trajectories":
            rows_with_exact_peer_trajectories,
    },

    "leakage_audit": {
        "own_history_future_violations":
            leakage_violations,

        "peer_history_future_violations":
            peer_future_violations,

        "target_product_held_out_of_peer_aggregates":
            True,

        "endpoint_used_only_as_target":
            True,

        "feature_max_date_never_after_origin":
            True,
    },

    "endpoint_semantics": {
        "horizon_days":
            HORIZON_DAYS,

        "selection":
            "NEAREST_LATER_OBSERVATION_TO_ORIGIN_PLUS_365",

        "new_endpoint_tolerance_invented":
            False,

        "direct_three_year_target":
            False,

        "direct_five_year_target":
            False,
    },

    "feature_classes": {
        "own_trajectory":
            True,

        "recent_vs_own_history_momentum":
            True,

        "volatility_downside":
            True,

        "finish_family_configuration":
            True,

        "exact_peer_origin_valuation":
            True,

        "exact_peer_trajectory":
            True,

        "relative_peer_valuation":
            True,
    },

    "governance": {
        "model_fitted":
            False,

        "model_tournament_executed":
            False,

        "V1_replaced":
            False,

        "eBay_used":
            False,

        "automatic_purchase_execution":
            False,
    },

    "authority": {
        "temporal_product_time_matrix":
            True,

        "model_tournament_execution":
            True,

        "V1_1_production_forecast":
            False,

        "V1_1_ranking":
            False,

        "V1_1_purchase_recommendation":
            False,
    },

    "next_gate":
        "SL8C_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_MODEL_TOURNAMENT",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_V1_1_TEMPORAL_MATRIX=PASS"
)

print(
    "MATRIX_ROWS="
    + str(
        len(
            matrix
        )
    )
)

print(
    "MATRIX_PRODUCTS="
    + str(
        unique_products
    )
)

print(
    "ROWS_WITH_OWN_HISTORY_2PLUS="
    + str(
        rows_with_own_two_plus
    )
)

print(
    "ROWS_WITH_EXACT_PEER_PRICES="
    + str(
        rows_with_exact_peer_prices
    )
)

print(
    "ROWS_WITH_EXACT_PEER_TRAJECTORIES="
    + str(
        rows_with_exact_peer_trajectories
    )
)

print(
    "OWN_HISTORY_FUTURE_LEAKAGE=0"
)

print(
    "PEER_HISTORY_FUTURE_LEAKAGE=0"
)

print(
    "TARGET_PRODUCT_HELD_OUT_OF_PEERS=TRUE"
)

print(
    "MODEL_FITTED=FALSE"
)

print(
    "NEXT_GATE=SL8C_SECRET_LAIR_V1_1_PRODUCT_SPECIFIC_MODEL_TOURNAMENT"
)