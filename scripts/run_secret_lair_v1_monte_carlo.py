from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np


HORIZON_DAYS = 365
PATHS_PER_HORIZON = 10_000
MAX_YEARS = 5

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


def deterministic_seed(
    product_id: str,
) -> int:

    payload = (
        "SECRET_LAIR_V1_SL5B|"
        + product_id
    ).encode(
        "utf-8"
    )

    digest = hashlib.sha256(
        payload
    ).hexdigest()

    seed = (
        int(
            digest[:15],
            16,
        )
        %
        2_147_483_646
    ) + 1

    return seed


def quantile_map(
    values: np.ndarray,
) -> dict[str, float]:

    result: dict[str, float] = {}

    for q in QUANTILES:

        name = (
            "q"
            + str(
                int(
                    q * 100
                )
            ).zfill(2)
        )

        result[name] = float(
            np.quantile(
                values,
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
    "--uncertainty",
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

parser.add_argument(
    "--expected-forecast-products",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-gap-products",
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

uncertainty_path = Path(
    args.uncertainty
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# Dynamic feature snapshot
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
# Reconstruct certified historical population
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
# Historical realized return events
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
                /
                origin.price
            )
            *
            (
                float(
                    HORIZON_DAYS
                )
                /
                float(
                    elapsed
                )
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
# Reconstruct EXACT SL-5A certified residual populations
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
        !=
        ESTABLISHED_CLASS
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

        # ---------------------------------------------------------------
        # Exact established COMMON_FOLD reproduction from SL-5A-R1.
        # ---------------------------------------------------------------

        established_common_fold = False

        if len(training) >= 2:

            origin_day = training[0].when

            x = np.asarray(
                [
                    (
                        row.when
                        -
                        origin_day
                    ).days
                    for row
                    in training
                ],
                dtype=float,
            )

            price_y = np.asarray(
                [
                    row.price
                    for row
                    in training
                ],
                dtype=float,
            )

            log_y = np.asarray(
                [
                    math.log(
                        row.price
                    )
                    for row
                    in training
                ],
                dtype=float,
            )

            if (
                len(
                    set(
                        x.tolist()
                    )
                )
                >= 2
            ):

                target_x = (
                    (
                        training[-1].when
                        -
                        origin_day
                    ).days
                    +
                    HORIZON_DAYS
                )

                linear_slope, linear_intercept = (
                    np.polyfit(
                        x,
                        price_y,
                        1,
                    )
                )

                candidate_linear = float(
                    linear_slope
                    *
                    target_x
                    +
                    linear_intercept
                )

                linear_valid = (
                    math.isfinite(
                        candidate_linear
                    )
                    and
                    candidate_linear > 0
                )

                log_slope, log_intercept = (
                    np.polyfit(
                        x,
                        log_y,
                        1,
                    )
                )

                candidate_log_value = float(
                    log_slope
                    *
                    target_x
                    +
                    log_intercept
                )

                try:
                    candidate_log_linear = (
                        math.exp(
                            candidate_log_value
                        )
                    )
                except OverflowError:
                    candidate_log_linear = (
                        float("inf")
                    )

                log_linear_valid = (
                    math.isfinite(
                        candidate_log_linear
                    )
                    and
                    candidate_log_linear > 0
                )

                daily_returns: list[
                    float
                ] = []

                for left, right in zip(
                    training,
                    training[1:],
                ):

                    elapsed_training = (
                        right.when
                        -
                        left.when
                    ).days

                    if elapsed_training <= 0:
                        continue

                    candidate_return = (
                        math.log(
                            right.price
                            /
                            left.price
                        )
                        /
                        float(
                            elapsed_training
                        )
                    )

                    if math.isfinite(
                        candidate_return
                    ):
                        daily_returns.append(
                            candidate_return
                        )

                median_valid = False

                if daily_returns:

                    median_daily = (
                        statistics.median(
                            daily_returns
                        )
                    )

                    try:
                        candidate_median = (
                            training[-1].price
                            *
                            math.exp(
                                median_daily
                                *
                                float(
                                    HORIZON_DAYS
                                )
                            )
                        )
                    except OverflowError:
                        candidate_median = (
                            float("inf")
                        )

                    median_valid = (
                        math.isfinite(
                            candidate_median
                        )
                        and
                        candidate_median > 0
                    )

                established_common_fold = (
                    linear_valid
                    and
                    log_linear_valid
                    and
                    median_valid
                )

        if established_common_fold:

            residual = math.log(
                endpoint.price
                /
                origin.price
            )

            if math.isfinite(
                residual
            ):
                established_residuals.append(
                    residual
                )

        # ---------------------------------------------------------------
        # Exact fallback COMMON_FOLD population:
        # both global and structural peers must exist.
        # ---------------------------------------------------------------

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

        if (
            global_returns
            and
            structural_returns
        ):

            peer_median = (
                statistics.median(
                    global_returns
                )
            )

            prediction = (
                origin.price
                *
                math.exp(
                    peer_median
                )
            )

            residual = math.log(
                endpoint.price
                /
                prediction
            )

            if math.isfinite(
                residual
            ):
                fallback_residuals.append(
                    residual
                )


if (
    len(established_residuals)
    !=
    args.expected_established_folds
):
    fail(
        "established residual-fold drift: "
        f"expected={args.expected_established_folds}, "
        f"actual={len(established_residuals)}"
    )


if (
    len(fallback_residuals)
    !=
    args.expected_fallback_folds
):
    fail(
        "fallback residual-fold drift: "
        f"expected={args.expected_fallback_folds}, "
        f"actual={len(fallback_residuals)}"
    )


established_array = np.asarray(
    established_residuals,
    dtype=float,
)

fallback_array = np.asarray(
    fallback_residuals,
    dtype=float,
)


# ---------------------------------------------------------------------------
# Production forecast snapshot
# ---------------------------------------------------------------------------

forecast_rows = read_csv(
    forecast_path
)

uncertainty_rows = read_csv(
    uncertainty_path
)

if not forecast_rows:
    fail(
        "production forecast ledger is empty"
    )

if (
    len(uncertainty_rows)
    != len(forecast_rows)
):
    fail(
        "forecast / uncertainty snapshot count mismatch"
    )


uncertainty_lookup = {
    clean(
        row.get(
            "secret_lair_id"
        )
    ):
        row

    for row
    in uncertainty_rows
}


risk_rows: list[
    dict[str, object]
] = []

seed_rows: list[
    dict[str, object]
] = []


simulated_products = 0
gap_products = 0
simulated_product_horizons = 0
terminal_outcomes_generated = 0


for row in sorted(
    forecast_rows,
    key=lambda item:
        clean(
            item.get(
                "secret_lair_id"
            )
        ),
):

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    product_name = clean(
        row.get(
            "product_name"
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

    point_1y = parse_positive_float(
        row.get(
            "one_year_forecast_usd"
        )
    )

    if product_id not in uncertainty_lookup:
        fail(
            "product missing from uncertainty ledger: "
            + product_id
        )


    # -----------------------------------------------------------------------
    # Explicit current-price / forecast gap.
    # Preserve all horizons as non-simulated rows.
    # -----------------------------------------------------------------------

    if (
        status
        !=
        "PRODUCTION_1Y_FORECAST"
    ):

        gap_products += 1

        for (
            horizon_code,
            years,
        ) in (
            ("Y1", 1),
            ("Y3", 3),
            ("Y5", 5),
        ):

            risk_rows.append(
                {
                    "secret_lair_id":
                        product_id,

                    "product_name":
                        product_name,

                    "production_method":
                        method,

                    "horizon_code":
                        horizon_code,

                    "horizon_years":
                        years,

                    "output_class":
                        (
                            "DIRECT_1Y_FORECAST_DISTRIBUTION"
                            if years == 1
                            else
                            "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED"
                        ),

                    "current_tcg_market_price_usd":
                        "",

                    "simulation_status":
                        "NO_SIMULATION_NO_GOVERNED_CURRENT_PRICE",

                    "paths":
                        0,

                    "seed":
                        "",

                    "expected_terminal_value_usd":
                        "",

                    "q05_terminal_value_usd":
                        "",

                    "q10_terminal_value_usd":
                        "",

                    "q25_terminal_value_usd":
                        "",

                    "q50_terminal_value_usd":
                        "",

                    "q75_terminal_value_usd":
                        "",

                    "q90_terminal_value_usd":
                        "",

                    "q95_terminal_value_usd":
                        "",

                    "expected_total_return":
                        "",

                    "median_total_return":
                        "",

                    "probability_of_loss":
                        "",

                    "probability_of_positive_return":
                        "",

                    "downside_tail_mean_terminal_value_usd":
                        "",

                    "upside_tail_mean_terminal_value_usd":
                        "",

                    "downside_tail_mean_total_return":
                        "",

                    "upside_tail_mean_total_return":
                        "",

                    "empirical_bootstrap":
                        False,

                    "gaussian_distribution_assumed":
                        False,

                    "direct_long_horizon_validation":
                        False,

                    "ranking_authorized":
                        False,

                    "purchase_recommendation_authorized":
                        False,
                }
            )

        continue


    if (
        current_price is None
        or
        point_1y is None
    ):
        fail(
            "authorized forecast missing current/point price: "
            + product_id
        )


    if method == "LAST_VALUE":

        residual_array = (
            established_array
        )

    elif (
        method
        ==
        "GLOBAL_PEER_MEDIAN_RETURN"
    ):

        residual_array = (
            fallback_array
        )

    else:

        fail(
            "unsupported production method in Monte Carlo: "
            + method
        )


    central_annual_log_return = (
        math.log(
            point_1y
            /
            current_price
        )
    )


    seed = deterministic_seed(
        product_id
    )

    rng = np.random.default_rng(
        seed
    )

    # Common random numbers across all product horizons.
    #
    # One 10,000 x 5 residual matrix is drawn.
    # Y1 = first column.
    # Y3 = first three columns.
    # Y5 = all five columns.

    sampled_residuals = rng.choice(
        residual_array,
        size=(
            PATHS_PER_HORIZON,
            MAX_YEARS,
        ),
        replace=True,
    )

    annual_log_returns = (
        central_annual_log_return
        +
        sampled_residuals
    )

    simulated_products += 1

    seed_rows.append(
        {
            "secret_lair_id":
                product_id,

            "product_name":
                product_name,

            "production_method":
                method,

            "seed":
                seed,

            "paths_per_horizon":
                PATHS_PER_HORIZON,

            "maximum_years_simulated":
                MAX_YEARS,

            "common_random_numbers_within_product":
                True,

            "seed_rule":
                "SHA256_SECRET_LAIR_V1_SL5B_PRODUCT_ID",

            "residual_population_size":
                len(
                    residual_array
                ),
        }
    )


    for (
        horizon_code,
        years,
    ) in (
        ("Y1", 1),
        ("Y3", 3),
        ("Y5", 5),
    ):

        cumulative_log_return = np.sum(
            annual_log_returns[
                :,
                :years
            ],
            axis=1,
        )

        terminal_values = (
            current_price
            *
            np.exp(
                cumulative_log_return
            )
        )

        if (
            not np.all(
                np.isfinite(
                    terminal_values
                )
            )
            or
            np.any(
                terminal_values <= 0
            )
        ):
            fail(
                "invalid Monte Carlo terminal values for "
                + product_id
                + " "
                + horizon_code
            )


        total_returns = (
            terminal_values
            /
            current_price
        ) - 1.0


        terminal_q = quantile_map(
            terminal_values
        )

        return_q = quantile_map(
            total_returns
        )


        if not (
            terminal_q["q05"]
            <= terminal_q["q10"]
            <= terminal_q["q25"]
            <= terminal_q["q50"]
            <= terminal_q["q75"]
            <= terminal_q["q90"]
            <= terminal_q["q95"]
        ):
            fail(
                "non-monotonic terminal quantiles for "
                + product_id
                + " "
                + horizon_code
            )


        probability_of_loss = float(
            np.mean(
                total_returns < 0
            )
        )

        probability_of_positive = float(
            np.mean(
                total_returns > 0
            )
        )


        downside_mask = (
            terminal_values
            <=
            terminal_q["q10"]
        )

        upside_mask = (
            terminal_values
            >=
            terminal_q["q90"]
        )


        downside_terminal_mean = float(
            np.mean(
                terminal_values[
                    downside_mask
                ]
            )
        )

        upside_terminal_mean = float(
            np.mean(
                terminal_values[
                    upside_mask
                ]
            )
        )

        downside_return_mean = float(
            np.mean(
                total_returns[
                    downside_mask
                ]
            )
        )

        upside_return_mean = float(
            np.mean(
                total_returns[
                    upside_mask
                ]
            )
        )


        risk_rows.append(
            {
                "secret_lair_id":
                    product_id,

                "product_name":
                    product_name,

                "production_method":
                    method,

                "horizon_code":
                    horizon_code,

                "horizon_years":
                    years,

                "output_class":
                    (
                        "DIRECT_1Y_FORECAST_DISTRIBUTION"
                        if years == 1
                        else
                        "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED"
                    ),

                "current_tcg_market_price_usd":
                    current_price,

                "simulation_status":
                    "MONTE_CARLO_SIMULATED",

                "paths":
                    PATHS_PER_HORIZON,

                "seed":
                    seed,

                "expected_terminal_value_usd":
                    float(
                        np.mean(
                            terminal_values
                        )
                    ),

                "q05_terminal_value_usd":
                    terminal_q["q05"],

                "q10_terminal_value_usd":
                    terminal_q["q10"],

                "q25_terminal_value_usd":
                    terminal_q["q25"],

                "q50_terminal_value_usd":
                    terminal_q["q50"],

                "q75_terminal_value_usd":
                    terminal_q["q75"],

                "q90_terminal_value_usd":
                    terminal_q["q90"],

                "q95_terminal_value_usd":
                    terminal_q["q95"],

                "expected_total_return":
                    float(
                        np.mean(
                            total_returns
                        )
                    ),

                "median_total_return":
                    return_q["q50"],

                "probability_of_loss":
                    probability_of_loss,

                "probability_of_positive_return":
                    probability_of_positive,

                "downside_tail_mean_terminal_value_usd":
                    downside_terminal_mean,

                "upside_tail_mean_terminal_value_usd":
                    upside_terminal_mean,

                "downside_tail_mean_total_return":
                    downside_return_mean,

                "upside_tail_mean_total_return":
                    upside_return_mean,

                "empirical_bootstrap":
                    True,

                "gaussian_distribution_assumed":
                    False,

                "direct_long_horizon_validation":
                    (
                        True
                        if years == 1
                        else False
                    ),

                "ranking_authorized":
                    False,

                "purchase_recommendation_authorized":
                    False,
            }
        )

        simulated_product_horizons += 1

        terminal_outcomes_generated += (
            PATHS_PER_HORIZON
        )


if (
    simulated_products
    !=
    args.expected_forecast_products
):
    fail(
        "simulated product coverage drift: "
        f"expected={args.expected_forecast_products}, "
        f"actual={simulated_products}"
    )


if (
    gap_products
    !=
    args.expected_gap_products
):
    fail(
        "Monte Carlo gap coverage drift: "
        f"expected={args.expected_gap_products}, "
        f"actual={gap_products}"
    )


expected_product_horizons = (
    simulated_products
    * 3
)

if (
    simulated_product_horizons
    !=
    expected_product_horizons
):
    fail(
        "simulated product-horizon count mismatch"
    )


expected_terminal_outcomes = (
    simulated_products
    *
    3
    *
    PATHS_PER_HORIZON
)

if (
    terminal_outcomes_generated
    !=
    expected_terminal_outcomes
):
    fail(
        "terminal outcome count mismatch"
    )


risk_path = (
    run_root
    /
    "secret_lair_v1_monte_carlo_risk_distribution.csv"
)

seed_path = (
    run_root
    /
    "secret_lair_v1_monte_carlo_seed_registry.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_monte_carlo_summary.json"
)


write_csv(
    risk_path,
    risk_rows,
    [
        "secret_lair_id",
        "product_name",
        "production_method",
        "horizon_code",
        "horizon_years",
        "output_class",
        "current_tcg_market_price_usd",
        "simulation_status",
        "paths",
        "seed",
        "expected_terminal_value_usd",
        "q05_terminal_value_usd",
        "q10_terminal_value_usd",
        "q25_terminal_value_usd",
        "q50_terminal_value_usd",
        "q75_terminal_value_usd",
        "q90_terminal_value_usd",
        "q95_terminal_value_usd",
        "expected_total_return",
        "median_total_return",
        "probability_of_loss",
        "probability_of_positive_return",
        "downside_tail_mean_terminal_value_usd",
        "upside_tail_mean_terminal_value_usd",
        "downside_tail_mean_total_return",
        "upside_tail_mean_total_return",
        "empirical_bootstrap",
        "gaussian_distribution_assumed",
        "direct_long_horizon_validation",
        "ranking_authorized",
        "purchase_recommendation_authorized",
    ],
)


write_csv(
    seed_path,
    seed_rows,
    [
        "secret_lair_id",
        "product_name",
        "production_method",
        "seed",
        "paths_per_horizon",
        "maximum_years_simulated",
        "common_random_numbers_within_product",
        "seed_rule",
        "residual_population_size",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_MONTE_CARLO_RISK_DISTRIBUTION_COMPLETE",

    "paths_per_product_horizon":
        PATHS_PER_HORIZON,

    "snapshot_products":
        len(
            forecast_rows
        ),

    "simulated_products":
        simulated_products,

    "gap_products":
        gap_products,

    "simulated_product_horizons":
        simulated_product_horizons,

    "terminal_outcomes_generated":
        terminal_outcomes_generated,

    "residual_populations": {
        "LAST_VALUE":
            len(
                established_residuals
            ),

        "GLOBAL_PEER_MEDIAN_RETURN":
            len(
                fallback_residuals
            ),
    },

    "horizons": {
        "Y1": {
            "years":
                1,

            "output_class":
                "DIRECT_1Y_FORECAST_DISTRIBUTION",
        },

        "Y3": {
            "years":
                3,

            "output_class":
                "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED",
        },

        "Y5": {
            "years":
                5,

            "output_class":
                "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED",
        },
    },

    "simulation": {
        "engine":
            "EMPIRICAL_BOOTSTRAP_LOG_RETURN_PATHS",

        "gaussian_distribution_assumed":
            False,

        "deterministic_seed_registry":
            True,

        "common_random_numbers_within_product":
            True,

        "raw_path_matrix_persisted":
            False,

        "exact_replay_supported_by_seed_and_inputs":
            True,
    },

    "authority": {
        "monte_carlo":
            True,

        "risk_distribution":
            True,

        "ranking":
            False,

        "purchase_recommendation":
            False,

        "automatic_purchase_execution":
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
    "SECRET_LAIR_MONTE_CARLO=PASS"
)

print(
    "PATHS_PER_PRODUCT_HORIZON="
    + str(
        PATHS_PER_HORIZON
    )
)

print(
    "SIMULATED_PRODUCTS="
    + str(
        simulated_products
    )
)

print(
    "GAP_PRODUCTS="
    + str(
        gap_products
    )
)

print(
    "SIMULATED_PRODUCT_HORIZONS="
    + str(
        simulated_product_horizons
    )
)

print(
    "TERMINAL_OUTCOMES_GENERATED="
    + str(
        terminal_outcomes_generated
    )
)

print(
    "ESTABLISHED_RESIDUAL_POPULATION="
    + str(
        len(
            established_residuals
        )
    )
)

print(
    "FALLBACK_RESIDUAL_POPULATION="
    + str(
        len(
            fallback_residuals
        )
    )
)

print(
    "DETERMINISTIC_SEEDS=TRUE"
)

print(
    "COMMON_RANDOM_NUMBERS_WITHIN_PRODUCT=TRUE"
)

print(
    "GAUSSIAN_DISTRIBUTION_ASSUMED=FALSE"
)

print(
    "DIRECT_3Y_VALIDATION=FALSE"
)

print(
    "DIRECT_5Y_VALIDATION=FALSE"
)

print(
    "RANKING_AUTHORIZED=FALSE"
)

print(
    "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
)