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

import numpy as np


HORIZON_DAYS = 365

QUANTILES = (
    0.05,
    0.10,
    0.25,
    0.50,
    0.75,
    0.90,
    0.95,
)

ESTABLISHED_CLASS = (
    "ESTABLISHED_1Y_TOURNAMENT_CANDIDATE"
)


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


@dataclass(frozen=True)
class ReturnEvent:
    product_id: str
    endpoint_date: date
    annualized_log_return: float
    structural_key: tuple[str, str, str]


def structural_key(
    row: dict[str, str],
) -> tuple[str, str, str]:

    return (
        clean(
            row.get("finish")
        ).lower(),

        clean(
            row.get(
                "product_family"
            )
        ).lower(),

        clean(
            row.get(
                "sealed_configuration"
            )
        ).lower(),
    )


def nearest_endpoint(
    observations: list[Observation],
    origin_index: int,
) -> Observation | None:

    origin = observations[
        origin_index
    ]

    target = (
        origin.when
        + timedelta(
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

    return min(
        candidates,
        key=lambda row: (
            abs(
                (
                    row.when
                    - target
                ).days
            ),
            row.when,
        ),
    )


def numeric_quantiles(
    values: list[float],
) -> dict[str, float]:

    if not values:
        fail(
            "cannot calculate quantiles on empty population"
        )

    array = np.asarray(
        values,
        dtype=float,
    )

    result: dict[str, float] = {}

    for q in QUANTILES:

        key = "q" + str(
            int(q * 100)
        ).zfill(2)

        result[key] = float(
            np.quantile(
                array,
                q,
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
    "--forecasts",
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

parser.add_argument(
    "--expected-established-folds",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-fallback-folds",
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

forecast_path = Path(
    args.forecasts
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# Dynamic feature universe.
# ---------------------------------------------------------------------------

feature_rows = read_csv(
    feature_path
)

if not feature_rows:
    fail(
        "feature matrix is empty"
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
            "blank feature identity"
        )

    if product_id in features:
        fail(
            "duplicate feature identity: "
            + product_id
        )

    features[
        product_id
    ] = row


# ---------------------------------------------------------------------------
# Reconstruct certified historical authority.
# ---------------------------------------------------------------------------

raw_history = read_csv(
    history_path
)

accepted: list[
    Observation
] = []

seen: set[str] = set()

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

    observation_key = "|".join(
        (
            product_id,
            when.isoformat(),
            source_record_id,
        )
    )

    if observation_key in seen:
        continue

    seen.add(
        observation_key
    )

    accepted.append(
        Observation(
            product_id=
                product_id,

            when=
                when,

            price=
                price,

            source_record_id=
                source_record_id,
        )
    )


if (
    len(accepted)
    !=
    args.expected_accepted_history_rows
):
    fail(
        "historical authority drift: "
        f"expected={args.expected_accepted_history_rows}, "
        f"actual={len(accepted)}"
    )


history_by_product: dict[
    str,
    list[Observation],
] = defaultdict(list)

for observation in accepted:

    history_by_product[
        observation.product_id
    ].append(
        observation
    )

for product_id in history_by_product:

    history_by_product[
        product_id
    ].sort(
        key=lambda row: (
            row.when,
            row.source_record_id,
        )
    )


# ---------------------------------------------------------------------------
# Realized return-event estate.
# ---------------------------------------------------------------------------

return_events: list[
    ReturnEvent
] = []

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
        len(observations)
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

        elapsed = (
            endpoint.when
            - origin.when
        ).days

        if elapsed <= 0:
            continue

        annualized_log_return = (
            math.log(
                endpoint.price
                / origin.price
            )
            * (
                float(HORIZON_DAYS)
                / float(elapsed)
            )
        )

        if not math.isfinite(
            annualized_log_return
        ):
            continue

        return_events.append(
            ReturnEvent(
                product_id=
                    product_id,

                endpoint_date=
                    endpoint.when,

                annualized_log_return=
                    annualized_log_return,

                structural_key=
                    key,
            )
        )


# ---------------------------------------------------------------------------
# Reconstruct the exact winner-calibration common folds.
#
# ESTABLISHED:
#   common-fold population requires enough own history for all established
#   tournament candidates, so origin training count must be >= 2.
#
# FALLBACK:
#   common-fold population requires BOTH structural and global peer routes
#   to have been available, matching SL-4A common-fold comparison.
# ---------------------------------------------------------------------------

established_residuals: list[
    float
] = []

fallback_residuals: list[
    float
] = []


for product_id in sorted(
    features.keys()
):

    feature = features[
        product_id
    ]

    if (
        clean(
            feature.get(
                "modeling_method_class"
            )
        )
        != ESTABLISHED_CLASS
    ):
        continue

    observations = history_by_product.get(
        product_id,
        [],
    )

    if len(observations) < 2:
        continue

    target_key = structural_key(
        feature
    )

    for origin_index in range(
        len(observations)
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

        training = [
            row
            for row
            in observations
            if row.when <= origin.when
        ]

        # Reproduce the ACTUAL SL-4A established COMMON_FOLDS population.
        #
        # SL-4A compared the four established models only on the intersection
        # of fold IDs where ALL FOUR models emitted a valid prediction.
        #
        # Therefore len(training) >= 2 is necessary but not sufficient.

        established_common_fold = False

        if len(training) >= 2:

            origin_day = training[0].when

            x = np.asarray(
                [
                    (
                        row.when
                        - origin_day
                    ).days
                    for row in training
                ],
                dtype=float,
            )

            price_y = np.asarray(
                [
                    row.price
                    for row in training
                ],
                dtype=float,
            )

            log_y = np.asarray(
                [
                    math.log(
                        row.price
                    )
                    for row in training
                ],
                dtype=float,
            )

            distinct_x = len(
                set(
                    x.tolist()
                )
            )

            linear_prediction = None
            log_linear_prediction = None
            median_log_return_prediction = None

            if distinct_x >= 2:

                linear_slope, linear_intercept = np.polyfit(
                    x,
                    price_y,
                    1,
                )

                target_x = (
                    (
                        training[-1].when
                        - origin_day
                    ).days
                    + HORIZON_DAYS
                )

                candidate_linear = float(
                    linear_slope
                    * target_x
                    + linear_intercept
                )

                if (
                    math.isfinite(
                        candidate_linear
                    )
                    and candidate_linear > 0
                ):
                    linear_prediction = (
                        candidate_linear
                    )

                log_slope, log_intercept = np.polyfit(
                    x,
                    log_y,
                    1,
                )

                candidate_log_value = float(
                    log_slope
                    * target_x
                    + log_intercept
                )

                try:
                    candidate_log_linear = math.exp(
                        candidate_log_value
                    )
                except OverflowError:
                    candidate_log_linear = float(
                        "inf"
                    )

                if (
                    math.isfinite(
                        candidate_log_linear
                    )
                    and candidate_log_linear > 0
                ):
                    log_linear_prediction = (
                        candidate_log_linear
                    )

                daily_log_returns = []

                for left, right in zip(
                    training,
                    training[1:],
                ):

                    elapsed_training_days = (
                        right.when
                        - left.when
                    ).days

                    if elapsed_training_days <= 0:
                        continue

                    candidate_daily_return = (
                        math.log(
                            right.price
                            / left.price
                        )
                        /
                        float(
                            elapsed_training_days
                        )
                    )

                    if math.isfinite(
                        candidate_daily_return
                    ):
                        daily_log_returns.append(
                            candidate_daily_return
                        )

                if daily_log_returns:

                    median_daily_return = (
                        statistics.median(
                            daily_log_returns
                        )
                    )

                    try:
                        candidate_median_return = (
                            training[-1].price
                            *
                            math.exp(
                                median_daily_return
                                *
                                float(
                                    HORIZON_DAYS
                                )
                            )
                        )
                    except OverflowError:
                        candidate_median_return = (
                            float("inf")
                        )

                    if (
                        math.isfinite(
                            candidate_median_return
                        )
                        and
                        candidate_median_return > 0
                    ):
                        median_log_return_prediction = (
                            candidate_median_return
                        )

            # LAST_VALUE is valid because all accepted history prices
            # are positive. The other three must also be valid.
            established_common_fold = (
                linear_prediction is not None
                and
                log_linear_prediction is not None
                and
                median_log_return_prediction is not None
            )

        if established_common_fold:

            last_value_prediction = (
                origin.price
            )

            established_log_residual = (
                math.log(
                    endpoint.price
                    /
                    last_value_prediction
                )
            )

            if math.isfinite(
                established_log_residual
            ):
                established_residuals.append(
                    established_log_residual
                )

        global_returns: list[
            float
        ] = []

        structural_returns: list[
            float
        ] = []

        for event in return_events:

            if (
                event.product_id
                ==
                product_id
            ):
                continue

            if (
                event.endpoint_date
                >
                origin.when
            ):
                continue

            global_returns.append(
                event.annualized_log_return
            )

            if (
                event.structural_key
                ==
                target_key
            ):
                structural_returns.append(
                    event.annualized_log_return
                )

        # Matches fallback COMMON_FOLDS:
        # both structural and global route must exist.
        if (
            global_returns
            and structural_returns
        ):

            global_peer_median = (
                statistics.median(
                    global_returns
                )
            )

            global_prediction = (
                origin.price
                *
                math.exp(
                    global_peer_median
                )
            )

            fallback_log_residual = (
                math.log(
                    endpoint.price
                    /
                    global_prediction
                )
            )

            if math.isfinite(
                fallback_log_residual
            ):
                fallback_residuals.append(
                    fallback_log_residual
                )


if (
    len(established_residuals)
    !=
    args.expected_established_folds
):
    fail(
        "established common-fold reconstruction drift: "
        f"expected={args.expected_established_folds}, "
        f"actual={len(established_residuals)}"
    )


if (
    len(fallback_residuals)
    !=
    args.expected_fallback_folds
):
    fail(
        "fallback common-fold reconstruction drift: "
        f"expected={args.expected_fallback_folds}, "
        f"actual={len(fallback_residuals)}"
    )


established_quantiles = (
    numeric_quantiles(
        established_residuals
    )
)

fallback_quantiles = (
    numeric_quantiles(
        fallback_residuals
    )
)


calibration_rows = []

for method, residuals, quantiles in (
    (
        "LAST_VALUE",
        established_residuals,
        established_quantiles,
    ),
    (
        "GLOBAL_PEER_MEDIAN_RETURN",
        fallback_residuals,
        fallback_quantiles,
    ),
):

    calibration_rows.append(
        {
            "production_method":
                method,

            "oos_common_fold_count":
                len(residuals),

            "mean_log_residual":
                statistics.mean(
                    residuals
                ),

            "median_log_residual":
                statistics.median(
                    residuals
                ),

            "residual_standard_deviation":
                statistics.pstdev(
                    residuals
                ),

            "q05_log_residual":
                quantiles["q05"],

            "q10_log_residual":
                quantiles["q10"],

            "q25_log_residual":
                quantiles["q25"],

            "q50_log_residual":
                quantiles["q50"],

            "q75_log_residual":
                quantiles["q75"],

            "q90_log_residual":
                quantiles["q90"],

            "q95_log_residual":
                quantiles["q95"],

            "empirical_oos_calibration":
                True,

            "direct_3y_validation":
                False,

            "direct_5y_validation":
                False,
        }
    )


# ---------------------------------------------------------------------------
# Apply calibrated residual distributions to certified current forecasts.
# ---------------------------------------------------------------------------

forecast_rows = read_csv(
    forecast_path
)

if not forecast_rows:
    fail(
        "production forecast ledger is empty"
    )


output_rows: list[
    dict[str, object]
] = []

forecast_count = 0
gap_count = 0


for row in forecast_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    status = clean(
        row.get(
            "forecast_status"
        )
    )

    method = clean(
        row.get(
            "production_method"
        )
    )

    current_price = parse_positive_float(
        row.get(
            "current_tcg_market_price_usd"
        )
    )

    point_forecast = parse_positive_float(
        row.get(
            "one_year_forecast_usd"
        )
    )

    base = {
        "secret_lair_id":
            product_id,

        "product_name":
            clean(
                row.get(
                    "product_name"
                )
            ),

        "production_method":
            method,

        "current_tcg_market_price_usd":
            (
                ""
                if current_price is None
                else current_price
            ),

        "certified_1y_point_forecast_usd":
            (
                ""
                if point_forecast is None
                else point_forecast
            ),

        "forecast_status":
            status,
    }


    if (
        status
        !=
        "PRODUCTION_1Y_FORECAST"
    ):

        gap_count += 1

        base.update(
            {
                "uncertainty_status":
                    "NO_UNCERTAINTY_DISTRIBUTION_NO_PRODUCTION_FORECAST",

                "calibration_fold_count":
                    0,

                "probability_of_1y_loss":
                    "",

                "q05_1y_usd":
                    "",

                "q10_1y_usd":
                    "",

                "q25_1y_usd":
                    "",

                "q50_1y_usd":
                    "",

                "q75_1y_usd":
                    "",

                "q90_1y_usd":
                    "",

                "q95_1y_usd":
                    "",

                "three_year_downside_scenario_usd":
                    "",

                "three_year_base_scenario_usd":
                    "",

                "three_year_upside_scenario_usd":
                    "",

                "five_year_downside_scenario_usd":
                    "",

                "five_year_base_scenario_usd":
                    "",

                "five_year_upside_scenario_usd":
                    "",

                "three_year_output_class":
                    "NO_SCENARIO_NO_CURRENT_PRICE",

                "five_year_output_class":
                    "NO_SCENARIO_NO_CURRENT_PRICE",
            }
        )

        output_rows.append(
            base
        )

        continue


    if (
        current_price is None
        or point_forecast is None
    ):
        fail(
            "authorized forecast lacks valid current/point price: "
            + product_id
        )


    if method == "LAST_VALUE":

        residuals = (
            established_residuals
        )

    elif (
        method
        ==
        "GLOBAL_PEER_MEDIAN_RETURN"
    ):

        residuals = (
            fallback_residuals
        )

    else:
        fail(
            "unknown production method: "
            + method
        )


    central_log_return = (
        math.log(
            point_forecast
            /
            current_price
        )
    )

    calibrated_log_returns = [
        central_log_return
        + residual
        for residual
        in residuals
    ]

    calibrated_quantiles = (
        numeric_quantiles(
            calibrated_log_returns
        )
    )

    one_year_prices = {
        key:
            current_price
            *
            math.exp(value)

        for key, value
        in calibrated_quantiles.items()
    }


    probability_of_loss = (
        sum(
            1
            for value
            in calibrated_log_returns
            if value < 0
        )
        /
        float(
            len(
                calibrated_log_returns
            )
        )
    )


    # -----------------------------------------------------------------------
    # 3Y / 5Y are deliberately SCENARIOS.
    #
    # The annualized q10/q50/q90 calibrated 1Y log-return states are simply
    # compounded for the requested horizon.
    #
    # They are NOT called directly validated forecasts.
    # -----------------------------------------------------------------------

    q10_rate = (
        calibrated_quantiles[
            "q10"
        ]
    )

    q50_rate = (
        calibrated_quantiles[
            "q50"
        ]
    )

    q90_rate = (
        calibrated_quantiles[
            "q90"
        ]
    )


    three_year_downside = (
        current_price
        *
        math.exp(
            q10_rate
            * 3.0
        )
    )

    three_year_base = (
        current_price
        *
        math.exp(
            q50_rate
            * 3.0
        )
    )

    three_year_upside = (
        current_price
        *
        math.exp(
            q90_rate
            * 3.0
        )
    )


    five_year_downside = (
        current_price
        *
        math.exp(
            q10_rate
            * 5.0
        )
    )

    five_year_base = (
        current_price
        *
        math.exp(
            q50_rate
            * 5.0
        )
    )

    five_year_upside = (
        current_price
        *
        math.exp(
            q90_rate
            * 5.0
        )
    )


    values_to_check = [
        *one_year_prices.values(),
        three_year_downside,
        three_year_base,
        three_year_upside,
        five_year_downside,
        five_year_base,
        five_year_upside,
    ]

    if any(
        (
            not math.isfinite(value)
            or value <= 0
        )
        for value
        in values_to_check
    ):
        fail(
            "invalid scenario value for "
            + product_id
        )


    forecast_count += 1

    base.update(
        {
            "uncertainty_status":
                "EMPIRICAL_OOS_UNCERTAINTY_CALIBRATED",

            "calibration_fold_count":
                len(
                    residuals
                ),

            "probability_of_1y_loss":
                probability_of_loss,

            "q05_1y_usd":
                one_year_prices[
                    "q05"
                ],

            "q10_1y_usd":
                one_year_prices[
                    "q10"
                ],

            "q25_1y_usd":
                one_year_prices[
                    "q25"
                ],

            "q50_1y_usd":
                one_year_prices[
                    "q50"
                ],

            "q75_1y_usd":
                one_year_prices[
                    "q75"
                ],

            "q90_1y_usd":
                one_year_prices[
                    "q90"
                ],

            "q95_1y_usd":
                one_year_prices[
                    "q95"
                ],

            "three_year_downside_scenario_usd":
                three_year_downside,

            "three_year_base_scenario_usd":
                three_year_base,

            "three_year_upside_scenario_usd":
                three_year_upside,

            "five_year_downside_scenario_usd":
                five_year_downside,

            "five_year_base_scenario_usd":
                five_year_base,

            "five_year_upside_scenario_usd":
                five_year_upside,

            "three_year_output_class":
                "SCENARIO_NOT_DIRECTLY_VALIDATED",

            "five_year_output_class":
                "SCENARIO_NOT_DIRECTLY_VALIDATED",
        }
    )

    output_rows.append(
        base
    )


scenario_path = (
    run_root
    /
    "secret_lair_v1_uncertainty_and_scenarios.csv"
)

calibration_path = (
    run_root
    /
    "secret_lair_v1_uncertainty_calibration.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_uncertainty_and_scenarios_summary.json"
)


write_csv(
    calibration_path,
    calibration_rows,
    [
        "production_method",
        "oos_common_fold_count",
        "mean_log_residual",
        "median_log_residual",
        "residual_standard_deviation",
        "q05_log_residual",
        "q10_log_residual",
        "q25_log_residual",
        "q50_log_residual",
        "q75_log_residual",
        "q90_log_residual",
        "q95_log_residual",
        "empirical_oos_calibration",
        "direct_3y_validation",
        "direct_5y_validation",
    ],
)


write_csv(
    scenario_path,
    output_rows,
    [
        "secret_lair_id",
        "product_name",
        "production_method",
        "current_tcg_market_price_usd",
        "certified_1y_point_forecast_usd",
        "forecast_status",
        "uncertainty_status",
        "calibration_fold_count",
        "probability_of_1y_loss",
        "q05_1y_usd",
        "q10_1y_usd",
        "q25_1y_usd",
        "q50_1y_usd",
        "q75_1y_usd",
        "q90_1y_usd",
        "q95_1y_usd",
        "three_year_downside_scenario_usd",
        "three_year_base_scenario_usd",
        "three_year_upside_scenario_usd",
        "five_year_downside_scenario_usd",
        "five_year_base_scenario_usd",
        "five_year_upside_scenario_usd",
        "three_year_output_class",
        "five_year_output_class",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_EMPIRICAL_UNCERTAINTY_AND_SCENARIOS_COMPLETE",

    "snapshot_products":
        len(output_rows),

    "uncertainty_calibrated_products":
        forecast_count,

    "scenario_gap_products":
        gap_count,

    "calibration": {
        "established_method":
            "LAST_VALUE",

        "established_common_folds":
            len(
                established_residuals
            ),

        "fallback_method":
            "GLOBAL_PEER_MEDIAN_RETURN",

        "fallback_common_folds":
            len(
                fallback_residuals
            ),

        "residual_space":
            "LOG_PRICE",

        "quantiles": [
            0.05,
            0.10,
            0.25,
            0.50,
            0.75,
            0.90,
            0.95,
        ],
    },

    "long_horizon": {
        "three_year_direct_validation":
            False,

        "five_year_direct_validation":
            False,

        "three_year_output":
            "SCENARIO",

        "five_year_output":
            "SCENARIO",

        "scenario_rule":
            "COMPOUND_EMPIRICALLY_CALIBRATED_1Y_Q10_Q50_Q90_ANNUALIZED_LOG_RETURN",

        "scenario_is_direct_forecast":
            False,
    },

    "authority": {
        "uncertainty_calibration":
            True,

        "three_year_scenario":
            True,

        "five_year_scenario":
            True,

        "monte_carlo":
            False,

        "ranking":
            False,

        "purchase_recommendation":
            False,
    },
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_UNCERTAINTY_AND_SCENARIOS=PASS"
)

print(
    "ESTABLISHED_CALIBRATION_FOLDS="
    + str(
        len(
            established_residuals
        )
    )
)

print(
    "FALLBACK_CALIBRATION_FOLDS="
    + str(
        len(
            fallback_residuals
        )
    )
)

print(
    "UNCERTAINTY_CALIBRATED_PRODUCTS="
    + str(
        forecast_count
    )
)

print(
    "SCENARIO_GAP_PRODUCTS="
    + str(
        gap_count
    )
)

print(
    "DIRECT_3Y_VALIDATION=FALSE"
)

print(
    "DIRECT_5Y_VALIDATION=FALSE"
)

print(
    "THREE_YEAR_OUTPUT_CLASS=SCENARIO"
)

print(
    "FIVE_YEAR_OUTPUT_CLASS=SCENARIO"
)

print(
    "RANKING_AUTHORIZED=FALSE"
)

print(
    "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
)