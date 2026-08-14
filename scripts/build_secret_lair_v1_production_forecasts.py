from __future__ import annotations

import argparse
import csv
import json
import math

from datetime import datetime, timezone
from pathlib import Path


ESTABLISHED_CLASS = (
    "ESTABLISHED_1Y_TOURNAMENT_CANDIDATE"
)

SHORT_CLASS = (
    "SHORT_HISTORY_TOURNAMENT_CANDIDATE"
)

CURRENT_ONLY_CLASS = (
    "CURRENT_PRICE_ONLY_NEW_PRODUCT_CANDIDATE"
)

EVIDENCE_GAP_CLASS = (
    "CURRENT_AND_HISTORY_EVIDENCE_GAP"
)


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
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
        value_float = float(text)
    except ValueError:
        return None

    if (
        not math.isfinite(value_float)
        or value_float <= 0
    ):
        return None

    return value_float


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
    "--comparables",
    required=True,
)

parser.add_argument(
    "--run-root",
    required=True,
)

args = parser.parse_args()

feature_path = Path(
    args.features
)

comparable_path = Path(
    args.comparables
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# Load dynamic current snapshot.
#
# No product-count constant is used.
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
# Comparable assignment lookup.
# ---------------------------------------------------------------------------

comparable_rows = read_csv(
    comparable_path
)

comparables: dict[
    str,
    dict[str, str],
] = {}

for row in comparable_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank comparable target identity"
        )

    if product_id in comparables:
        fail(
            "duplicate comparable target: "
            + product_id
        )

    comparables[
        product_id
    ] = row


forecast_rows: list[
    dict[str, object]
] = []

forecast_generated_at = (
    datetime.now(
        timezone.utc
    ).isoformat()
)

authorized_current_price_count = 0
forecasted_count = 0
gap_count = 0

established_forecast_count = 0
fallback_forecast_count = 0

fallback_exact_comparables_count = 0
fallback_global_only_count = 0


for product_id in sorted(
    features.keys()
):

    feature = features[
        product_id
    ]

    product_name = clean(
        feature.get(
            "product_name"
        )
    )

    method_class = clean(
        feature.get(
            "modeling_method_class"
        )
    )

    current_price_status = clean(
        feature.get(
            "current_price_status"
        )
    )

    current_price = parse_positive_float(
        feature.get(
            "tcg_market_price_usd"
        )
    )

    current_price_authorized = (
        current_price_status
        ==
        "TCG_MARKET_PRICE_AUTHORIZED_V1"
        and current_price is not None
    )

    if current_price_authorized:
        authorized_current_price_count += 1

    forecast_status = ""
    production_method = ""
    forecast_price = None
    forecast_return = None

    comparable_class = ""
    exact_peer_count = 0
    global_peer_count = 0
    global_peer_event_count = 0
    exact_peer_ids = ""
    global_peer_ids = ""
    global_peer_median_log_return = None
    global_peer_dispersion = None

    # -----------------------------------------------------------------------
    # No governed current-price anchor = no dollar forecast.
    # -----------------------------------------------------------------------

    if not current_price_authorized:

        forecast_status = (
            "NO_PRODUCTION_FORECAST_NO_CURRENT_TCG_MARKET_PRICE"
        )

        production_method = (
            "NONE_CURRENT_PRICE_GAP"
        )

        gap_count += 1

    # -----------------------------------------------------------------------
    # Established-history route.
    #
    # Empirical SL-4A winner = LAST_VALUE.
    # -----------------------------------------------------------------------

    elif method_class == ESTABLISHED_CLASS:

        production_method = (
            "LAST_VALUE"
        )

        forecast_price = (
            current_price
        )

        forecast_return = 0.0

        forecast_status = (
            "PRODUCTION_1Y_FORECAST"
        )

        established_forecast_count += 1
        forecasted_count += 1

    # -----------------------------------------------------------------------
    # Short / new product route.
    #
    # Empirical SL-4A winner = GLOBAL_PEER_MEDIAN_RETURN.
    #
    # Exact structural comparables remain visible supporting evidence but
    # do not override the OOS tournament winner.
    # -----------------------------------------------------------------------

    elif method_class in (
        SHORT_CLASS,
        CURRENT_ONLY_CLASS,
    ):

        comparable = comparables.get(
            product_id
        )

        if comparable is None:
            fail(
                "fallback target missing comparable evidence: "
                + product_id
            )

        global_peer_count = int(
            clean(
                comparable.get(
                    "global_comparable_product_count"
                )
            )
            or "0"
        )

        exact_peer_count = int(
            clean(
                comparable.get(
                    "exact_structural_comparable_product_count"
                )
            )
            or "0"
        )

        global_peer_event_count = int(
            clean(
                comparable.get(
                    "global_comparable_event_count"
                )
            )
            or "0"
        )

        if global_peer_count <= 0:
            fail(
                "fallback target has zero global peer products: "
                + product_id
            )

        if global_peer_event_count <= 0:
            fail(
                "fallback target has zero realized peer events: "
                + product_id
            )

        global_peer_median_log_return = (
            parse_positive_float(
                comparable.get(
                    "global_median_annualized_log_return"
                )
            )
        )

        # Peer log return may legitimately be zero or negative.
        # Therefore parse separately from a positive-price parser.

        raw_peer_return = clean(
            comparable.get(
                "global_median_annualized_log_return"
            )
        )

        try:
            peer_log_return = float(
                raw_peer_return
            )
        except ValueError as exc:
            raise RuntimeError(
                "invalid global peer median log return for "
                + product_id
            ) from exc

        if not math.isfinite(
            peer_log_return
        ):
            fail(
                "non-finite peer return for "
                + product_id
            )

        raw_dispersion = clean(
            comparable.get(
                "global_return_dispersion"
            )
        )

        if raw_dispersion:

            try:
                global_peer_dispersion = float(
                    raw_dispersion
                )
            except ValueError as exc:
                raise RuntimeError(
                    "invalid global peer dispersion for "
                    + product_id
                ) from exc

            if (
                not math.isfinite(
                    global_peer_dispersion
                )
                or global_peer_dispersion < 0
            ):
                fail(
                    "invalid peer dispersion for "
                    + product_id
                )

        forecast_price = (
            current_price
            * math.exp(
                peer_log_return
            )
        )

        if (
            not math.isfinite(
                forecast_price
            )
            or forecast_price <= 0
        ):
            fail(
                "invalid peer forecast for "
                + product_id
            )

        forecast_return = (
            forecast_price
            / current_price
        ) - 1.0

        comparable_class = clean(
            comparable.get(
                "comparable_evidence_class"
            )
        )

        exact_peer_ids = clean(
            comparable.get(
                "exact_structural_comparable_ids"
            )
        )

        global_peer_ids = clean(
            comparable.get(
                "global_comparable_ids"
            )
        )

        production_method = (
            "GLOBAL_PEER_MEDIAN_RETURN"
        )

        forecast_status = (
            "PRODUCTION_1Y_FORECAST"
        )

        fallback_forecast_count += 1
        forecasted_count += 1

        if exact_peer_count > 0:
            fallback_exact_comparables_count += 1
        else:
            fallback_global_only_count += 1

    elif method_class == EVIDENCE_GAP_CLASS:

        # This class should normally have no current price under SL-3C.
        # If a later refresh changes that state, the feature/method matrix must
        # be refreshed before forecasting rather than silently guessing a route.

        fail(
            "evidence-gap product has current price but no refreshed "
            "method assignment: "
            + product_id
        )

    else:

        fail(
            "unknown modeling method class for "
            + product_id
            + ": "
            + method_class
        )


    forecast_rows.append(
        {
            "secret_lair_id":
                product_id,

            "product_name":
                product_name,

            "finish":
                clean(
                    feature.get(
                        "finish"
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

            "modeling_method_class":
                method_class,

            "current_price_status":
                current_price_status,

            "current_tcg_market_price_usd":
                (
                    ""
                    if current_price is None
                    else current_price
                ),

            "forecast_horizon_days":
                365,

            "production_method":
                production_method,

            "one_year_forecast_usd":
                (
                    ""
                    if forecast_price is None
                    else forecast_price
                ),

            "one_year_forecast_return":
                (
                    ""
                    if forecast_return is None
                    else forecast_return
                ),

            "forecast_status":
                forecast_status,

            "comparable_evidence_class":
                comparable_class,

            "exact_structural_comparable_product_count":
                exact_peer_count,

            "global_comparable_product_count":
                global_peer_count,

            "global_comparable_event_count":
                global_peer_event_count,

            "exact_structural_comparable_ids":
                exact_peer_ids,

            "global_comparable_ids":
                global_peer_ids,

            "global_peer_median_annualized_log_return":
                (
                    ""
                    if production_method
                    != "GLOBAL_PEER_MEDIAN_RETURN"
                    else peer_log_return
                ),

            "global_peer_return_dispersion":
                (
                    ""
                    if global_peer_dispersion is None
                    else global_peer_dispersion
                ),

            "target_product_excluded_from_peer_population":
                (
                    production_method
                    ==
                    "GLOBAL_PEER_MEDIAN_RETURN"
                ),

            "exact_structural_peer_used_to_override_tournament_winner":
                False,

            "low_price_used_as_market_fallback":
                False,

            "three_year_direct_validation":
                False,

            "three_year_output_status":
                "SCENARIO_PENDING",

            "five_year_direct_validation":
                False,

            "five_year_output_status":
                "SCENARIO_PENDING",

            "forecast_generated_at_utc":
                forecast_generated_at,

            "ranking_authorized":
                False,

            "purchase_recommendation_authorized":
                False,
        }
    )


# ---------------------------------------------------------------------------
# Snapshot invariants.
#
# Every current-price-authorized product must receive exactly one 1Y forecast.
# No product without a current-price authority may receive one.
# ---------------------------------------------------------------------------

if (
    forecasted_count
    != authorized_current_price_count
):
    fail(
        "forecast coverage does not equal governed current-price coverage: "
        f"forecasted={forecasted_count}, "
        f"authorized_current_price={authorized_current_price_count}"
    )


forecasted_rows = [
    row
    for row in forecast_rows
    if row[
        "forecast_status"
    ]
    ==
    "PRODUCTION_1Y_FORECAST"
]

gap_rows = [
    row
    for row in forecast_rows
    if row[
        "forecast_status"
    ]
    !=
    "PRODUCTION_1Y_FORECAST"
]

for row in gap_rows:

    if clean(
        row.get(
            "one_year_forecast_usd"
        )
    ):
        fail(
            "forecast gap contains fabricated dollar forecast: "
            + str(
                row[
                    "secret_lair_id"
                ]
            )
        )


ledger_path = (
    run_root
    / "secret_lair_v1_production_forecast_1y.csv"
)

summary_path = (
    run_root
    / "secret_lair_v1_production_forecast_summary.json"
)


write_csv(
    ledger_path,
    forecast_rows,
    [
        "secret_lair_id",
        "product_name",
        "finish",
        "product_family",
        "sealed_configuration",
        "modeling_method_class",
        "current_price_status",
        "current_tcg_market_price_usd",
        "forecast_horizon_days",
        "production_method",
        "one_year_forecast_usd",
        "one_year_forecast_return",
        "forecast_status",
        "comparable_evidence_class",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "global_comparable_event_count",
        "exact_structural_comparable_ids",
        "global_comparable_ids",
        "global_peer_median_annualized_log_return",
        "global_peer_return_dispersion",
        "target_product_excluded_from_peer_population",
        "exact_structural_peer_used_to_override_tournament_winner",
        "low_price_used_as_market_fallback",
        "three_year_direct_validation",
        "three_year_output_status",
        "five_year_direct_validation",
        "five_year_output_status",
        "forecast_generated_at_utc",
        "ranking_authorized",
        "purchase_recommendation_authorized",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_PRODUCTION_1Y_FORECAST_BUILD_COMPLETE",

    "snapshot_products":
        len(forecast_rows),

    "authorized_current_price_products":
        authorized_current_price_count,

    "production_1y_forecasts":
        forecasted_count,

    "forecast_gaps":
        len(gap_rows),

    "established_last_value_forecasts":
        established_forecast_count,

    "fallback_global_peer_forecasts":
        fallback_forecast_count,

    "fallback_forecasts_with_exact_structural_support":
        fallback_exact_comparables_count,

    "fallback_forecasts_with_global_only_support":
        fallback_global_only_count,

    "methods": {
        "established":
            "LAST_VALUE",

        "short_history":
            "GLOBAL_PEER_MEDIAN_RETURN",

        "current_price_only_new_product":
            "GLOBAL_PEER_MEDIAN_RETURN",

        "no_current_price":
            "NO_PRODUCTION_DOLLAR_FORECAST",
    },

    "governance": {
        "fixed_universe_count":
            False,

        "arbitrary_age_exclusion":
            False,

        "target_product_peer_holdout":
            True,

        "low_price_market_fallback":
            False,

        "exact_peer_override_of_empirical_winner":
            False,

        "three_year_direct_validation":
            False,

        "five_year_direct_validation":
            False,

        "three_year_scenario":
            "PENDING",

        "five_year_scenario":
            "PENDING",

        "ranking_authorized":
            False,

        "purchase_recommendation_authorized":
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
    "SECRET_LAIR_PRODUCTION_1Y_FORECAST_BUILD=PASS"
)

print(
    "SNAPSHOT_PRODUCTS="
    + str(
        len(forecast_rows)
    )
)

print(
    "AUTHORIZED_CURRENT_PRICE_PRODUCTS="
    + str(
        authorized_current_price_count
    )
)

print(
    "PRODUCTION_1Y_FORECASTS="
    + str(
        forecasted_count
    )
)

print(
    "FORECAST_GAPS="
    + str(
        len(gap_rows)
    )
)

print(
    "ESTABLISHED_LAST_VALUE_FORECASTS="
    + str(
        established_forecast_count
    )
)

print(
    "FALLBACK_GLOBAL_PEER_FORECASTS="
    + str(
        fallback_forecast_count
    )
)

print(
    "FALLBACK_WITH_EXACT_STRUCTURAL_SUPPORT="
    + str(
        fallback_exact_comparables_count
    )
)

print(
    "FALLBACK_GLOBAL_ONLY_SUPPORT="
    + str(
        fallback_global_only_count
    )
)

print(
    "FORECAST_COVERAGE_EQUALS_CURRENT_PRICE_AUTHORITY=TRUE"
)

print(
    "LOW_PRICE_MARKET_FALLBACK=FALSE"
)

print(
    "TARGET_PRODUCT_PEER_HOLDOUT=TRUE"
)

print(
    "FIXED_UNIVERSE_COUNT=FALSE"
)

print(
    "RANKING_AUTHORIZED=FALSE"
)

print(
    "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
)