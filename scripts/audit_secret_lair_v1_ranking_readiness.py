from __future__ import annotations

import argparse
import csv
import json
import math

from collections import Counter, defaultdict
from pathlib import Path


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_float(
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


def parse_int(
    value: object,
) -> int:

    text = clean(value)

    if not text:
        return 0

    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_bool(
    value: object,
) -> bool:

    return clean(value).lower() in (
        "true",
        "1",
        "yes",
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


parser = argparse.ArgumentParser()

parser.add_argument(
    "--features",
    required=True,
)

parser.add_argument(
    "--forecasts",
    required=True,
)

parser.add_argument(
    "--comparables",
    required=True,
)

parser.add_argument(
    "--risk",
    required=True,
)

parser.add_argument(
    "--run-root",
    required=True,
)

parser.add_argument(
    "--expected-simulated-products",
    required=True,
    type=int,
)

args = parser.parse_args()


feature_rows = read_csv(
    Path(args.features)
)

forecast_rows = read_csv(
    Path(args.forecasts)
)

comparable_rows = read_csv(
    Path(args.comparables)
)

risk_rows = read_csv(
    Path(args.risk)
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


features = {
    clean(
        row.get(
            "secret_lair_id"
        )
    ): row

    for row
    in feature_rows
}


forecasts = {
    clean(
        row.get(
            "secret_lair_id"
        )
    ): row

    for row
    in forecast_rows
}


comparables = {
    clean(
        row.get(
            "secret_lair_id"
        )
    ): row

    for row
    in comparable_rows
}


risk_by_product: dict[
    str,
    dict[str, dict[str, str]],
] = defaultdict(dict)

for row in risk_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    horizon = clean(
        row.get(
            "horizon_code"
        )
    )

    if horizon in risk_by_product[
        product_id
    ]:
        fail(
            "duplicate product/horizon risk row: "
            + product_id
            + " "
            + horizon
        )

    risk_by_product[
        product_id
    ][
        horizon
    ] = row


forecastable_ids = [
    product_id
    for product_id, row
    in forecasts.items()
    if clean(
        row.get(
            "forecast_status"
        )
    )
    ==
    "PRODUCTION_1Y_FORECAST"
]


if (
    len(forecastable_ids)
    !=
    args.expected_simulated_products
):
    fail(
        "forecastable product count drift: "
        f"expected={args.expected_simulated_products}, "
        f"actual={len(forecastable_ids)}"
    )


audit_rows: list[
    dict[str, object]
] = []


# ---------------------------------------------------------------------------
# A theoretical risk signature intentionally excludes:
#
#   - Monte Carlo seed;
#   - Monte Carlo sample means/quantiles;
#   - current dollar price.
#
# This prevents random-seed noise or expensive-product bias from being
# mistaken for genuine investment-return differentiation.
#
# The signature is built from:
#
#   production method
#   certified central annual log return
#   certified residual population identity
#
# Products sharing this signature have the same underlying modeled
# return distribution before finite Monte Carlo sampling.
# ---------------------------------------------------------------------------

signature_members: dict[
    str,
    list[str],
] = defaultdict(list)


for product_id in sorted(
    forecastable_ids
):

    forecast = forecasts[
        product_id
    ]

    feature = features.get(
        product_id
    )

    if feature is None:
        fail(
            "forecast product missing feature row: "
            + product_id
        )

    method = clean(
        forecast.get(
            "production_method"
        )
    )

    current_price = parse_float(
        forecast.get(
            "current_tcg_market_price_usd"
        )
    )

    point_price = parse_float(
        forecast.get(
            "one_year_forecast_usd"
        )
    )

    if (
        current_price is None
        or current_price <= 0
        or point_price is None
        or point_price <= 0
    ):
        fail(
            "invalid production price/forecast for "
            + product_id
        )


    annual_log_return = math.log(
        point_price
        /
        current_price
    )


    if method == "LAST_VALUE":

        residual_population = (
            "ESTABLISHED_6632"
        )

    elif (
        method
        ==
        "GLOBAL_PEER_MEDIAN_RETURN"
    ):

        residual_population = (
            "FALLBACK_4829"
        )

    else:

        fail(
            "unexpected production method: "
            + method
        )


    # More precision than is economically meaningful, while grouping values
    # that are genuinely the same production return anchor.
    central_return_key = (
        f"{annual_log_return:.12f}"
    )


    signature = "|".join(
        (
            method,
            central_return_key,
            residual_population,
        )
    )

    signature_members[
        signature
    ].append(
        product_id
    )


# ---------------------------------------------------------------------------
# Build product-level audit.
# ---------------------------------------------------------------------------

for product_id in sorted(
    forecastable_ids
):

    forecast = forecasts[
        product_id
    ]

    feature = features[
        product_id
    ]

    method = clean(
        forecast.get(
            "production_method"
        )
    )

    current_price = parse_float(
        forecast.get(
            "current_tcg_market_price_usd"
        )
    )

    point_price = parse_float(
        forecast.get(
            "one_year_forecast_usd"
        )
    )

    annual_log_return = math.log(
        point_price
        /
        current_price
    )

    residual_population = (
        "ESTABLISHED_6632"
        if method == "LAST_VALUE"
        else
        "FALLBACK_4829"
    )

    signature = "|".join(
        (
            method,
            f"{annual_log_return:.12f}",
            residual_population,
        )
    )

    signature_size = len(
        signature_members[
            signature
        ]
    )


    risk_horizons = risk_by_product.get(
        product_id,
        {}
    )

    if set(
        risk_horizons.keys()
    ) != {
        "Y1",
        "Y3",
        "Y5",
    }:
        fail(
            "missing governed risk horizons for "
            + product_id
        )


    y1 = risk_horizons["Y1"]

    mc_median_return = parse_float(
        y1.get(
            "median_total_return"
        )
    )

    mc_probability_positive = (
        parse_float(
            y1.get(
                "probability_of_positive_return"
            )
        )
    )

    mc_downside_tail = parse_float(
        y1.get(
            "downside_tail_mean_total_return"
        )
    )


    comparable = comparables.get(
        product_id
    )

    exact_peer_count = 0
    global_peer_count = 0
    exact_peer_events = 0
    global_peer_events = 0
    comparable_class = (
        "NOT_APPLICABLE_ESTABLISHED_ROUTE"
    )

    if comparable is not None:

        exact_peer_count = parse_int(
            comparable.get(
                "exact_structural_comparable_product_count"
            )
        )

        global_peer_count = parse_int(
            comparable.get(
                "global_comparable_product_count"
            )
        )

        exact_peer_events = parse_int(
            comparable.get(
                "exact_structural_comparable_event_count"
            )
        )

        global_peer_events = parse_int(
            comparable.get(
                "global_comparable_event_count"
            )
        )

        comparable_class = clean(
            comparable.get(
                "comparable_evidence_class"
            )
        )


    historical_observations = parse_int(
        feature.get(
            "historical_observation_count"
        )
    )

    history_span_days = parse_int(
        feature.get(
            "history_span_days"
        )
    )


    simulation_noise_rank_risk = (
        signature_size > 1
    )


    audit_rows.append(
        {
            "secret_lair_id":
                product_id,

            "product_name":
                clean(
                    forecast.get(
                        "product_name"
                    )
                ),

            "modeling_method_class":
                clean(
                    forecast.get(
                        "modeling_method_class"
                    )
                ),

            "production_method":
                method,

            "central_1y_log_return":
                annual_log_return,

            "underlying_risk_signature":
                signature,

            "products_sharing_underlying_risk_signature":
                signature_size,

            "unique_underlying_return_profile":
                signature_size == 1,

            "simulation_noise_rank_risk":
                simulation_noise_rank_risk,

            "mc_y1_median_return":
                mc_median_return,

            "mc_y1_probability_positive":
                mc_probability_positive,

            "mc_y1_downside_tail_mean_return":
                mc_downside_tail,

            "historical_observation_count":
                historical_observations,

            "history_span_days":
                history_span_days,

            "comparable_evidence_class":
                comparable_class,

            "exact_structural_comparable_product_count":
                exact_peer_count,

            "global_comparable_product_count":
                global_peer_count,

            "exact_structural_comparable_event_count":
                exact_peer_events,

            "global_comparable_event_count":
                global_peer_events,

            "current_price_level_allowed_as_quality_signal":
                False,

            "monte_carlo_seed_allowed_as_tie_break":
                False,

            "ranking_score_created":
                False,

            "purchase_recommendation_created":
                False,
        }
    )


unique_signatures = len(
    signature_members
)

largest_signature_group = max(
    len(members)
    for members
    in signature_members.values()
)

products_in_shared_signatures = sum(
    len(members)
    for members
    in signature_members.values()
    if len(members) > 1
)

products_with_unique_signatures = sum(
    1
    for row
    in audit_rows
    if bool(
        row[
            "unique_underlying_return_profile"
        ]
    )
)


method_counts = Counter(
    row[
        "production_method"
    ]
    for row
    in audit_rows
)


# ---------------------------------------------------------------------------
# Determine whether ranking can be built directly from the modeled return
# distributions.
#
# IMPORTANT:
# No arbitrary minimum percentage is imposed.
#
# If ANY products share an identical underlying modeled return distribution,
# their Monte Carlo sample differences may not be used to order those products.
#
# This does not necessarily block ranking. It means an explicit governed
# non-simulation evidence/tie architecture is required before final ranking.
# ---------------------------------------------------------------------------

shared_profile_exists = (
    products_in_shared_signatures
    > 0
)


if shared_profile_exists:

    readiness_status = (
        "RANKING_REQUIRES_GOVERNED_TIE_AND_EVIDENCE_ARCHITECTURE"
    )

    next_gate = (
        "SL6A2_SECRET_LAIR_RANKING_SIGNAL_AND_TIE_ARCHITECTURE"
    )

    direct_ranking_authorized = False

else:

    readiness_status = (
        "RETURN_DISTRIBUTIONS_DISTINCT_FOR_DIRECT_RANKING"
    )

    next_gate = (
        "SL6B_SECRET_LAIR_RANKING_EXECUTION"
    )

    direct_ranking_authorized = True


ledger_path = (
    run_root
    /
    "secret_lair_v1_ranking_readiness_audit.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_ranking_readiness_summary.json"
)


write_csv(
    ledger_path,
    audit_rows,
    [
        "secret_lair_id",
        "product_name",
        "modeling_method_class",
        "production_method",
        "central_1y_log_return",
        "underlying_risk_signature",
        "products_sharing_underlying_risk_signature",
        "unique_underlying_return_profile",
        "simulation_noise_rank_risk",
        "mc_y1_median_return",
        "mc_y1_probability_positive",
        "mc_y1_downside_tail_mean_return",
        "historical_observation_count",
        "history_span_days",
        "comparable_evidence_class",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "exact_structural_comparable_event_count",
        "global_comparable_event_count",
        "current_price_level_allowed_as_quality_signal",
        "monte_carlo_seed_allowed_as_tie_break",
        "ranking_score_created",
        "purchase_recommendation_created",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_RANKING_READINESS_AUDIT_COMPLETE",

    "readiness_status":
        readiness_status,

    "forecastable_products":
        len(
            audit_rows
        ),

    "production_method_counts":
        dict(
            method_counts
        ),

    "underlying_return_profiles": {
        "unique_signature_count":
            unique_signatures,

        "products_with_unique_signature":
            products_with_unique_signatures,

        "products_in_shared_signatures":
            products_in_shared_signatures,

        "largest_shared_signature_group":
            largest_signature_group,

        "shared_profile_exists":
            shared_profile_exists,
    },

    "ranking_governance": {
        "monte_carlo_seed_may_break_ties":
            False,

        "current_dollar_price_may_proxy_investment_quality":
            False,

        "arbitrary_ranking_weights_introduced":
            False,

        "precollector_ranking_weights_reused":
            False,

        "direct_ranking_execution_authorized":
            direct_ranking_authorized,

        "ranking_certified":
            False,

        "purchase_analysis":
            False,

        "purchase_recommendation":
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
    "SECRET_LAIR_RANKING_READINESS_AUDIT=PASS"
)

print(
    "FORECASTABLE_PRODUCTS="
    + str(
        len(
            audit_rows
        )
    )
)

print(
    "UNIQUE_UNDERLYING_RETURN_PROFILES="
    + str(
        unique_signatures
    )
)

print(
    "PRODUCTS_WITH_UNIQUE_RETURN_PROFILE="
    + str(
        products_with_unique_signatures
    )
)

print(
    "PRODUCTS_IN_SHARED_RETURN_PROFILES="
    + str(
        products_in_shared_signatures
    )
)

print(
    "LARGEST_SHARED_PROFILE_GROUP="
    + str(
        largest_signature_group
    )
)

print(
    "MONTE_CARLO_SEED_MAY_BREAK_TIES=FALSE"
)

print(
    "CURRENT_PRICE_LEVEL_MAY_PROXY_QUALITY=FALSE"
)

print(
    "ARBITRARY_RANKING_WEIGHTS_INTRODUCED=FALSE"
)

print(
    "PRECOLLECTOR_RANKING_WEIGHTS_REUSED=FALSE"
)

print(
    "READINESS_STATUS="
    + readiness_status
)

print(
    "DIRECT_RANKING_EXECUTION_AUTHORIZED="
    + str(
        direct_ranking_authorized
    ).upper()
)

print(
    "NEXT_GATE="
    + next_gate
)