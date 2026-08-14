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

ESTABLISHED_MODELS = (
    "LAST_VALUE",
    "LINEAR_PRICE_TREND",
    "LOG_LINEAR_TREND",
    "MEDIAN_LOG_RETURN_TREND",
)

FALLBACK_MODELS = (
    "STRUCTURAL_PEER_MEDIAN_RETURN",
    "GLOBAL_PEER_MEDIAN_RETURN",
)

ALL_MODELS = (
    *ESTABLISHED_MODELS,
    *FALLBACK_MODELS,
)


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_date(value: object) -> date:
    text = clean(value)

    if not text:
        raise ValueError("blank date")

    return date.fromisoformat(text[:10])


def parse_positive_float(
    value: object,
) -> float | None:

    text = clean(value)

    if not text:
        return None

    try:
        number = float(text)
    except ValueError:
        return None

    if (
        not math.isfinite(number)
        or number <= 0
    ):
        return None

    return number


def read_csv(
    path: Path,
) -> list[dict[str, str]]:

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


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


@dataclass(frozen=True)
class Observation:
    product_id: str
    when: date
    price: float
    source_name: str
    source_record_id: str


@dataclass(frozen=True)
class ReturnEvent:
    product_id: str
    origin_date: date
    endpoint_date: date
    endpoint_elapsed_days: int
    annualized_log_return: float
    structural_key: tuple[str, str, str]


def structural_key(
    feature: dict[str, str],
) -> tuple[str, str, str]:

    return (
        clean(feature.get("finish")).lower(),
        clean(feature.get("product_family")).lower(),
        clean(
            feature.get(
                "sealed_configuration"
            )
        ).lower(),
    )


def nearest_endpoint(
    observations: list[Observation],
    origin_index: int,
    horizon_days: int,
) -> tuple[int, Observation] | None:

    origin = observations[origin_index]

    target = (
        origin.when
        + timedelta(days=horizon_days)
    )

    if target > observations[-1].when:
        return None

    candidates: list[
        tuple[int, Observation]
    ] = []

    for index in range(
        origin_index + 1,
        len(observations),
    ):
        endpoint = observations[index]

        if endpoint.when <= origin.when:
            continue

        candidates.append(
            (index, endpoint)
        )

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda item: (
            abs(
                (
                    item[1].when
                    - target
                ).days
            ),
            item[1].when,
        ),
    )


def predict_last_value(
    training: list[Observation],
) -> float | None:

    if not training:
        return None

    return training[-1].price


def predict_linear_price_trend(
    training: list[Observation],
    horizon_days: int,
) -> float | None:

    if len(training) < 2:
        return None

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

    y = np.asarray(
        [row.price for row in training],
        dtype=float,
    )

    if len(set(x.tolist())) < 2:
        return None

    slope, intercept = np.polyfit(
        x,
        y,
        1,
    )

    target_x = (
        training[-1].when
        - origin_day
    ).days + horizon_days

    prediction = float(
        slope * target_x
        + intercept
    )

    if (
        not math.isfinite(prediction)
        or prediction <= 0
    ):
        return None

    return prediction


def predict_log_linear_trend(
    training: list[Observation],
    horizon_days: int,
) -> float | None:

    if len(training) < 2:
        return None

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

    y = np.asarray(
        [
            math.log(row.price)
            for row in training
        ],
        dtype=float,
    )

    if len(set(x.tolist())) < 2:
        return None

    slope, intercept = np.polyfit(
        x,
        y,
        1,
    )

    target_x = (
        training[-1].when
        - origin_day
    ).days + horizon_days

    log_prediction = float(
        slope * target_x
        + intercept
    )

    prediction = math.exp(
        log_prediction
    )

    if (
        not math.isfinite(prediction)
        or prediction <= 0
    ):
        return None

    return prediction


def predict_median_log_return(
    training: list[Observation],
    horizon_days: int,
) -> float | None:

    if len(training) < 2:
        return None

    daily_log_returns: list[float] = []

    for left, right in zip(
        training,
        training[1:],
    ):
        elapsed = (
            right.when
            - left.when
        ).days

        if elapsed <= 0:
            continue

        value = (
            math.log(
                right.price
                / left.price
            )
            / float(elapsed)
        )

        if math.isfinite(value):
            daily_log_returns.append(
                value
            )

    if not daily_log_returns:
        return None

    median_daily = statistics.median(
        daily_log_returns
    )

    prediction = (
        training[-1].price
        * math.exp(
            median_daily
            * float(horizon_days)
        )
    )

    if (
        not math.isfinite(prediction)
        or prediction <= 0
    ):
        return None

    return prediction


def peer_prediction(
    *,
    origin_price: float,
    target_product_id: str,
    target_structural_key: tuple[str, str, str],
    origin_date: date,
    events: list[ReturnEvent],
    structural_only: bool,
) -> tuple[float | None, int]:

    eligible: list[float] = []

    for event in events:

        # Product holdout:
        # target product is prohibited from contributing.
        if (
            event.product_id
            == target_product_id
        ):
            continue

        # Anti-leakage:
        # peer return must already be fully realized
        # by the target fold's origin date.
        if event.endpoint_date > origin_date:
            continue

        if (
            structural_only
            and event.structural_key
            != target_structural_key
        ):
            continue

        eligible.append(
            event.annualized_log_return
        )

    if not eligible:
        return None, 0

    median_return = statistics.median(
        eligible
    )

    prediction = (
        origin_price
        * math.exp(median_return)
    )

    if (
        not math.isfinite(prediction)
        or prediction <= 0
    ):
        return None, len(eligible)

    return prediction, len(eligible)


def metrics(
    rows: list[dict[str, object]],
) -> dict[str, object]:

    if not rows:
        return {
            "prediction_count": 0,
            "product_count": 0,
            "smape": "",
            "mae": "",
            "rmse": "",
            "median_ape": "",
            "bias": "",
            "absolute_bias": "",
            "directional_accuracy": "",
        }

    predictions = np.asarray(
        [
            float(row["prediction"])
            for row in rows
        ],
        dtype=float,
    )

    actual = np.asarray(
        [
            float(row["actual_endpoint_price"])
            for row in rows
        ],
        dtype=float,
    )

    origins = np.asarray(
        [
            float(row["origin_price"])
            for row in rows
        ],
        dtype=float,
    )

    errors = predictions - actual

    absolute_errors = np.abs(errors)

    denominator = (
        np.abs(predictions)
        + np.abs(actual)
    )

    smape_values = np.where(
        denominator > 0,
        (
            2.0
            * absolute_errors
            / denominator
        ),
        0.0,
    )

    ape_values = (
        absolute_errors
        / actual
    )

    predicted_direction = np.sign(
        predictions - origins
    )

    actual_direction = np.sign(
        actual - origins
    )

    directional = np.mean(
        predicted_direction
        == actual_direction
    )

    bias = float(
        np.mean(errors)
    )

    return {
        "prediction_count":
            len(rows),

        "product_count":
            len(
                {
                    str(
                        row["secret_lair_id"]
                    )
                    for row in rows
                }
            ),

        "smape":
            float(
                np.mean(smape_values)
            ),

        "mae":
            float(
                np.mean(absolute_errors)
            ),

        "rmse":
            float(
                math.sqrt(
                    np.mean(
                        errors ** 2
                    )
                )
            ),

        "median_ape":
            float(
                np.median(ape_values)
            ),

        "bias":
            bias,

        "absolute_bias":
            abs(bias),

        "directional_accuracy":
            float(directional),
    }


def select_winner(
    score_rows: list[dict[str, object]],
    route: str,
) -> str:

    candidates = [
        row
        for row in score_rows
        if (
            row["route"] == route
            and row["evaluation_scope"]
            == "COMMON_FOLDS"
            and int(
                row["prediction_count"]
            ) > 0
        )
    ]

    if not candidates:
        fail(
            f"no common-fold score rows for route {route}"
        )

    ordered = sorted(
        candidates,
        key=lambda row: (
            float(row["smape"]),
            float(row["mae"]),
            float(
                row["absolute_bias"]
            ),
            str(row["model"]),
        ),
    )

    return str(
        ordered[0]["model"]
    )


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

history_path = Path(args.history)
features_path = Path(args.features)
run_root = Path(args.run_root)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)

feature_rows = read_csv(
    features_path
)

if not feature_rows:
    fail("feature matrix is empty")

features: dict[
    str,
    dict[str, str],
] = {}

for row in feature_rows:

    product_id = clean(
        row.get("secret_lair_id")
    )

    if not product_id:
        fail(
            "blank identity in feature matrix"
        )

    if product_id in features:
        fail(
            "duplicate feature identity: "
            + product_id
        )

    features[product_id] = row


# ---------------------------------------------------------------------------
# Reconstruct the already-certified SL-3B accepted history population.
# No low-price fallback. No eBay.
# ---------------------------------------------------------------------------

raw_history = read_csv(
    history_path
)

accepted_history: list[
    Observation
] = []

seen_observations: set[str] = set()

for row in raw_history:

    product_id = clean(
        row.get("secret_lair_id")
    )

    if product_id not in features:
        continue

    source_name = clean(
        row.get("source_name")
    )

    # V1 TCG-only history.
    if source_name not in (
        "TCGCSV",
        "TCGCSV_ARCHIVE_MONTHLY",
    ):
        continue

    source_record_id = clean(
        row.get("source_record_id")
    )

    source_file = clean(
        row.get("source_file")
    )

    if (
        not source_record_id
        or not source_file
    ):
        continue

    price = parse_positive_float(
        row.get("market_price")
    )

    if price is None:
        continue

    try:
        when = parse_date(
            row.get("observation_date")
        )
    except Exception:
        continue

    key = "|".join(
        (
            product_id,
            when.isoformat(),
            source_record_id,
        )
    )

    if key in seen_observations:
        continue

    seen_observations.add(key)

    accepted_history.append(
        Observation(
            product_id=product_id,
            when=when,
            price=price,
            source_name=source_name,
            source_record_id=source_record_id,
        )
    )


if (
    len(accepted_history)
    != args.expected_accepted_history_rows
):
    fail(
        "reconstructed accepted history does not match "
        "certified SL-3B population: "
        f"expected={args.expected_accepted_history_rows}, "
        f"actual={len(accepted_history)}"
    )


history_by_product: dict[
    str,
    list[Observation],
] = defaultdict(list)

for row in accepted_history:
    history_by_product[
        row.product_id
    ].append(row)

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
# Create realized historical 1Y return events.
#
# These are later used only when their endpoint was already realized before
# a peer forecast origin. This prevents future leakage.
# ---------------------------------------------------------------------------

return_events: list[
    ReturnEvent
] = []

for product_id, observations in (
    history_by_product.items()
):

    feature = features[product_id]

    key = structural_key(feature)

    for origin_index in range(
        len(observations)
    ):

        endpoint_result = nearest_endpoint(
            observations,
            origin_index,
            HORIZON_DAYS,
        )

        if endpoint_result is None:
            continue

        _, endpoint = endpoint_result

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
                product_id=product_id,
                origin_date=origin.when,
                endpoint_date=endpoint.when,
                endpoint_elapsed_days=elapsed,
                annualized_log_return=
                    annualized_log_return,
                structural_key=key,
            )
        )


# ---------------------------------------------------------------------------
# Temporal OOS folds.
#
# Established-history products are identified by the certified SL-3C method
# class, not by a hard-coded product count.
# ---------------------------------------------------------------------------

fold_predictions: list[
    dict[str, object]
] = []

fold_index = 0

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
        "ESTABLISHED_1Y_TOURNAMENT_CANDIDATE"
    ):
        continue

    observations = history_by_product.get(
        product_id,
        [],
    )

    if len(observations) < 2:
        continue

    product_key = structural_key(
        feature
    )

    for origin_index in range(
        len(observations)
    ):

        endpoint_result = nearest_endpoint(
            observations,
            origin_index,
            HORIZON_DAYS,
        )

        if endpoint_result is None:
            continue

        endpoint_index, endpoint = (
            endpoint_result
        )

        origin = observations[
            origin_index
        ]

        training = [
            row
            for row in observations
            if row.when <= origin.when
        ]

        fold_index += 1

        fold_id = (
            f"{product_id}|"
            f"{origin.when.isoformat()}|"
            f"{fold_index:08d}"
        )

        actual_change = (
            endpoint.price
            - origin.price
        )

        realized_days = (
            endpoint.when
            - origin.when
        ).days

        horizon_error_days = (
            realized_days
            - HORIZON_DAYS
        )

        predictions: dict[
            str,
            tuple[float | None, int]
        ] = {}

        predictions["LAST_VALUE"] = (
            predict_last_value(
                training
            ),
            0,
        )

        predictions[
            "LINEAR_PRICE_TREND"
        ] = (
            predict_linear_price_trend(
                training,
                HORIZON_DAYS,
            ),
            0,
        )

        predictions[
            "LOG_LINEAR_TREND"
        ] = (
            predict_log_linear_trend(
                training,
                HORIZON_DAYS,
            ),
            0,
        )

        predictions[
            "MEDIAN_LOG_RETURN_TREND"
        ] = (
            predict_median_log_return(
                training,
                HORIZON_DAYS,
            ),
            0,
        )

        predictions[
            "STRUCTURAL_PEER_MEDIAN_RETURN"
        ] = peer_prediction(
            origin_price=origin.price,
            target_product_id=product_id,
            target_structural_key=
                product_key,
            origin_date=origin.when,
            events=return_events,
            structural_only=True,
        )

        predictions[
            "GLOBAL_PEER_MEDIAN_RETURN"
        ] = peer_prediction(
            origin_price=origin.price,
            target_product_id=product_id,
            target_structural_key=
                product_key,
            origin_date=origin.when,
            events=return_events,
            structural_only=False,
        )

        for (
            model,
            (
                prediction,
                peer_event_count,
            ),
        ) in predictions.items():

            if prediction is None:
                continue

            fold_predictions.append(
                {
                    "fold_id":
                        fold_id,

                    "secret_lair_id":
                        product_id,

                    "origin_date":
                        origin.when.isoformat(),

                    "target_date":
                        (
                            origin.when
                            + timedelta(
                                days=HORIZON_DAYS
                            )
                        ).isoformat(),

                    "actual_endpoint_date":
                        endpoint.when.isoformat(),

                    "target_horizon_days":
                        HORIZON_DAYS,

                    "actual_endpoint_elapsed_days":
                        realized_days,

                    "horizon_error_days":
                        horizon_error_days,

                    "training_observation_count":
                        len(training),

                    "model":
                        model,

                    "route":
                        (
                            "ESTABLISHED"
                            if model
                            in ESTABLISHED_MODELS
                            else "FALLBACK"
                        ),

                    "origin_price":
                        origin.price,

                    "prediction":
                        prediction,

                    "actual_endpoint_price":
                        endpoint.price,

                    "actual_change":
                        actual_change,

                    "prediction_error":
                        prediction
                        - endpoint.price,

                    "absolute_error":
                        abs(
                            prediction
                            - endpoint.price
                        ),

                    "peer_event_count":
                        peer_event_count,

                    "target_product_excluded_from_peer_training":
                        (
                            model
                            in FALLBACK_MODELS
                        ),

                    "future_peer_events_prohibited":
                        (
                            model
                            in FALLBACK_MODELS
                        ),

                    "future_target_product_observations_in_training":
                        False,
                }
            )


if not fold_predictions:
    fail(
        "tournament produced zero temporal OOS predictions"
    )


# ---------------------------------------------------------------------------
# Common-fold comparison.
#
# Established models compare only on folds where all established models
# produced a prediction.
#
# Fallback models compare only on folds where both peer models produced a
# prediction.
#
# This avoids comparing metrics on different evaluation populations.
# ---------------------------------------------------------------------------

predictions_by_model: dict[
    str,
    dict[str, dict[str, object]],
] = defaultdict(dict)

for row in fold_predictions:

    predictions_by_model[
        str(row["model"])
    ][
        str(row["fold_id"])
    ] = row


def common_fold_ids(
    models: tuple[str, ...],
) -> set[str]:

    sets: list[set[str]] = []

    for model in models:

        fold_map = predictions_by_model.get(
            model,
            {},
        )

        sets.append(
            set(fold_map.keys())
        )

    if not sets:
        return set()

    result = sets[0]

    for values in sets[1:]:
        result = result.intersection(
            values
        )

    return result


established_common = common_fold_ids(
    ESTABLISHED_MODELS
)

fallback_common = common_fold_ids(
    FALLBACK_MODELS
)

if not established_common:
    fail(
        "no common folds across established-history models"
    )

if not fallback_common:
    fail(
        "no common folds across fallback peer models"
    )


score_rows: list[
    dict[str, object]
] = []

for model in ALL_MODELS:

    route = (
        "ESTABLISHED"
        if model in ESTABLISHED_MODELS
        else "FALLBACK"
    )

    all_rows = list(
        predictions_by_model[
            model
        ].values()
    )

    all_metrics = metrics(
        all_rows
    )

    score_rows.append(
        {
            "route":
                route,

            "model":
                model,

            "evaluation_scope":
                "ALL_AVAILABLE_FOLDS",

            **all_metrics,
        }
    )

    common_ids = (
        established_common
        if route == "ESTABLISHED"
        else fallback_common
    )

    common_rows = [
        predictions_by_model[
            model
        ][fold_id]
        for fold_id
        in sorted(common_ids)
    ]

    common_metrics = metrics(
        common_rows
    )

    score_rows.append(
        {
            "route":
                route,

            "model":
                model,

            "evaluation_scope":
                "COMMON_FOLDS",

            **common_metrics,
        }
    )


established_winner = select_winner(
    score_rows,
    "ESTABLISHED",
)

fallback_winner = select_winner(
    score_rows,
    "FALLBACK",
)


# ---------------------------------------------------------------------------
# Product-level OOS summaries.
# ---------------------------------------------------------------------------

product_model_rows: dict[
    tuple[str, str],
    list[dict[str, object]],
] = defaultdict(list)

for row in fold_predictions:

    product_model_rows[
        (
            str(row["secret_lair_id"]),
            str(row["model"]),
        )
    ].append(row)


product_summary: list[
    dict[str, object]
] = []

for (
    product_id,
    model,
), rows in sorted(
    product_model_rows.items()
):

    result = metrics(rows)

    product_summary.append(
        {
            "secret_lair_id":
                product_id,

            "model":
                model,

            "route":
                (
                    "ESTABLISHED"
                    if model
                    in ESTABLISHED_MODELS
                    else "FALLBACK"
                ),

            **result,
        }
    )


# ---------------------------------------------------------------------------
# Winner score rows.
# ---------------------------------------------------------------------------

def score_for(
    model: str,
    route: str,
) -> dict[str, object]:

    matches = [
        row
        for row in score_rows
        if (
            row["model"] == model
            and row["route"] == route
            and row["evaluation_scope"]
            == "COMMON_FOLDS"
        )
    ]

    if len(matches) != 1:
        fail(
            f"winner score row missing for {model}"
        )

    return matches[0]


established_winner_score = score_for(
    established_winner,
    "ESTABLISHED",
)

fallback_winner_score = score_for(
    fallback_winner,
    "FALLBACK",
)


# ---------------------------------------------------------------------------
# Persist evidence.
# ---------------------------------------------------------------------------

fold_ledger_path = (
    run_root
    / "secret_lair_v1_temporal_oos_fold_ledger.csv"
)

scorecard_path = (
    run_root
    / "secret_lair_v1_model_tournament_scorecard.csv"
)

product_summary_path = (
    run_root
    / "secret_lair_v1_model_tournament_product_summary.csv"
)

summary_path = (
    run_root
    / "secret_lair_v1_model_tournament_summary.json"
)


write_csv(
    fold_ledger_path,
    fold_predictions,
    [
        "fold_id",
        "secret_lair_id",
        "origin_date",
        "target_date",
        "actual_endpoint_date",
        "target_horizon_days",
        "actual_endpoint_elapsed_days",
        "horizon_error_days",
        "training_observation_count",
        "model",
        "route",
        "origin_price",
        "prediction",
        "actual_endpoint_price",
        "actual_change",
        "prediction_error",
        "absolute_error",
        "peer_event_count",
        "target_product_excluded_from_peer_training",
        "future_peer_events_prohibited",
        "future_target_product_observations_in_training",
    ],
)

write_csv(
    scorecard_path,
    score_rows,
    [
        "route",
        "model",
        "evaluation_scope",
        "prediction_count",
        "product_count",
        "smape",
        "mae",
        "rmse",
        "median_ape",
        "bias",
        "absolute_bias",
        "directional_accuracy",
    ],
)

write_csv(
    product_summary_path,
    product_summary,
    [
        "secret_lair_id",
        "model",
        "route",
        "prediction_count",
        "product_count",
        "smape",
        "mae",
        "rmse",
        "median_ape",
        "bias",
        "absolute_bias",
        "directional_accuracy",
    ],
)


horizon_errors = [
    int(
        row["horizon_error_days"]
    )
    for row in fold_predictions
    if row["model"] == "LAST_VALUE"
]

summary = {
    "status":
        "SECRET_LAIR_V1_MODEL_TOURNAMENT_EXECUTED",

    "horizon_days":
        HORIZON_DAYS,

    "accepted_history_rows":
        len(accepted_history),

    "history_products":
        len(history_by_product),

    "realized_return_events":
        len(return_events),

    "temporal_prediction_rows":
        len(fold_predictions),

    "established_common_fold_count":
        len(established_common),

    "fallback_common_fold_count":
        len(fallback_common),

    "established_winner":
        established_winner,

    "fallback_winner":
        fallback_winner,

    "established_winner_metrics":
        established_winner_score,

    "fallback_winner_metrics":
        fallback_winner_score,

    "endpoint_sampling": {
        "rule":
            "NEAREST_REALIZED_OBSERVATION_TO_ORIGIN_PLUS_365_DAYS",

        "minimum_horizon_error_days":
            min(horizon_errors),

        "maximum_horizon_error_days":
            max(horizon_errors),

        "median_absolute_horizon_error_days":
            statistics.median(
                abs(value)
                for value
                in horizon_errors
            ),
    },

    "selection_rule": {
        "evaluation_population":
            "COMMON_TEMPORAL_FOLDS_WITHIN_ROUTE",

        "order": [
            "LOWEST_SMAPE",
            "LOWEST_MAE",
            "LOWEST_ABSOLUTE_BIAS",
            "DETERMINISTIC_MODEL_NAME_TIE_BREAK",
        ],

        "weighted_composite_score":
            False,

        "minimum_fold_threshold":
            False,
    },

    "anti_leakage": {
        "temporal_order_required":
            True,

        "future_target_observations_in_training":
            False,

        "peer_return_endpoint_must_precede_or_equal_forecast_origin":
            True,

        "target_product_excluded_from_peer_training":
            True,

        "random_time_split":
            False,
    },

    "long_horizons": {
        "three_year_direct_validation":
            False,

        "five_year_direct_validation":
            False,

        "three_year_output_class":
            "SCENARIO",

        "five_year_output_class":
            "SCENARIO",
    },

    "authority": {
        "tournament_evidence":
            True,

        "winner_method_certification":
            False,

        "production_forecast":
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
    "SECRET_LAIR_MODEL_TOURNAMENT_EXECUTION=PASS"
)

print(
    "ACCEPTED_HISTORY_ROWS="
    + str(
        len(accepted_history)
    )
)

print(
    "HISTORY_PRODUCTS="
    + str(
        len(history_by_product)
    )
)

print(
    "REALIZED_1Y_RETURN_EVENTS="
    + str(
        len(return_events)
    )
)

print(
    "TEMPORAL_PREDICTION_ROWS="
    + str(
        len(fold_predictions)
    )
)

print(
    "ESTABLISHED_COMMON_FOLDS="
    + str(
        len(established_common)
    )
)

print(
    "FALLBACK_COMMON_FOLDS="
    + str(
        len(fallback_common)
    )
)

print(
    "ESTABLISHED_WINNER="
    + established_winner
)

print(
    "FALLBACK_WINNER="
    + fallback_winner
)

print(
    "ESTABLISHED_WINNER_SMAPE="
    + str(
        established_winner_score["smape"]
    )
)

print(
    "ESTABLISHED_WINNER_MAE="
    + str(
        established_winner_score["mae"]
    )
)

print(
    "FALLBACK_WINNER_SMAPE="
    + str(
        fallback_winner_score["smape"]
    )
)

print(
    "FALLBACK_WINNER_MAE="
    + str(
        fallback_winner_score["mae"]
    )
)

print(
    "MINIMUM_FOLD_THRESHOLD=FALSE"
)

print(
    "FIXED_UNIVERSE_COUNT=FALSE"
)

print(
    "RANDOM_TIME_SPLIT=FALSE"
)

print(
    "PRODUCT_HOLDOUT_FOR_PEER_MODELS=TRUE"
)

print(
    "THREE_YEAR_DIRECT_VALIDATION=FALSE"
)

print(
    "FIVE_YEAR_DIRECT_VALIDATION=FALSE"
)

print(
    "PRODUCTION_FORECAST_AUTHORIZED=FALSE"
)