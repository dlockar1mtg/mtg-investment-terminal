from __future__ import annotations

import argparse
import csv
import json
import math
import statistics

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path


DAYS_PER_YEAR = 365.0


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

    return (
        numerator
        /
        denominator
    )


def max_drawdown(
    prices: list[float],
) -> float | None:

    if not prices:
        return None

    running_high = prices[0]

    worst = 0.0

    for price in prices:

        running_high = max(
            running_high,
            price,
        )

        drawdown = (
            price
            /
            running_high
        ) - 1.0

        worst = min(
            worst,
            drawdown,
        )

    return worst


def blank_if_none(
    value: object,
) -> object:

    if value is None:
        return ""

    return value


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
    "--expected-history-rows",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-products",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-products-with-history",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-current-price-products",
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
# 1. Dynamic Secret Lair feature universe
# ---------------------------------------------------------------------------

feature_rows = read_csv(
    feature_path
)

if len(feature_rows) != args.expected_products:
    fail(
        "feature-universe snapshot drift: "
        f"expected={args.expected_products}, "
        f"actual={len(feature_rows)}"
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
            "blank Secret Lair identity"
        )

    if product_id in features:
        fail(
            "duplicate Secret Lair identity: "
            + product_id
        )

    features[
        product_id
    ] = row


# ---------------------------------------------------------------------------
# 2. Reconstruct EXACT certified historical TCG authority
#
# This intentionally preserves the existing V1 acceptance semantics.
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


if len(accepted) != args.expected_history_rows:

    fail(
        "historical authority drift: "
        f"expected={args.expected_history_rows}, "
        f"actual={len(accepted)}"
    )


# ---------------------------------------------------------------------------
# 3. Product/date uniqueness
#
# Product-time features require one governed market price for one product/date.
#
# We DO NOT invent a duplicate-date aggregation rule.
#
# Exact duplicate prices may collapse safely.
# Conflicting same-date prices fail closed for future adjudication.
# ---------------------------------------------------------------------------

date_prices: dict[
    tuple[str, date],
    set[float],
] = defaultdict(set)


for observation in accepted:

    date_prices[
        (
            observation.product_id,
            observation.when,
        )
    ].add(
        observation.price
    )


for (
    product_date,
    prices,
) in date_prices.items():

    if len(prices) > 1:

        fail(
            "conflicting accepted market prices on same product/date: "
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

    price = next(
        iter(
            prices
        )
    )

    history_by_product[
        product_id
    ].append(
        Observation(
            product_id=
                product_id,

            when=
                when,

            price=
                price,

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


if (
    len(
        history_by_product
    )
    !=
    args.expected_products_with_history
):

    fail(
        "products-with-history drift: "
        f"expected={args.expected_products_with_history}, "
        f"actual={len(history_by_product)}"
    )


# ---------------------------------------------------------------------------
# 4. Own-product trajectory features
# ---------------------------------------------------------------------------

own_metrics: dict[
    str,
    dict[str, object],
] = {}


for product_id in features:

    observations = history_by_product.get(
        product_id,
        [],
    )

    metrics: dict[
        str,
        object
    ] = {
        "history_observation_count":
            len(
                observations
            ),

        "history_first_date":
            "",

        "history_last_date":
            "",

        "history_span_days":
            0,

        "history_start_price_usd":
            "",

        "history_last_price_usd":
            "",

        "full_history_total_return":
            "",

        "full_history_annualized_log_return":
            "",

        "full_history_log_price_slope_per_day":
            "",

        "full_history_log_price_slope_annualized":
            "",

        "latest_interval_days":
            "",

        "latest_interval_log_return":
            "",

        "latest_interval_annualized_log_return":
            "",

        "median_interval_annualized_log_return":
            "",

        "latest_minus_median_interval_annualized_log_return":
            "",

        "interval_annualized_log_return_volatility":
            "",

        "downside_interval_semideviation":
            "",

        "positive_interval_fraction":
            "",

        "negative_interval_fraction":
            "",

        "maximum_historical_drawdown":
            "",

        "historical_median_price_usd":
            "",

        "historical_low_price_usd":
            "",

        "historical_high_price_usd":
            "",
    }

    if observations:

        prices = [
            row.price
            for row
            in observations
        ]

        metrics[
            "history_first_date"
        ] = (
            observations[0]
            .when
            .isoformat()
        )

        metrics[
            "history_last_date"
        ] = (
            observations[-1]
            .when
            .isoformat()
        )

        metrics[
            "history_start_price_usd"
        ] = prices[0]

        metrics[
            "history_last_price_usd"
        ] = prices[-1]

        metrics[
            "historical_median_price_usd"
        ] = statistics.median(
            prices
        )

        metrics[
            "historical_low_price_usd"
        ] = min(
            prices
        )

        metrics[
            "historical_high_price_usd"
        ] = max(
            prices
        )

        metrics[
            "maximum_historical_drawdown"
        ] = max_drawdown(
            prices
        )

    if len(observations) >= 2:

        first = observations[0]
        last = observations[-1]

        span_days = (
            last.when
            - first.when
        ).days

        metrics[
            "history_span_days"
        ] = span_days

        metrics[
            "full_history_total_return"
        ] = (
            last.price
            /
            first.price
        ) - 1.0

        if span_days > 0:

            full_log_return = math.log(
                last.price
                /
                first.price
            )

            metrics[
                "full_history_annualized_log_return"
            ] = (
                full_log_return
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
                        - first.when
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

                metrics[
                    "full_history_log_price_slope_per_day"
                ] = daily_slope

                metrics[
                    "full_history_log_price_slope_annualized"
                ] = (
                    daily_slope
                    *
                    DAYS_PER_YEAR
                )

        interval_returns: list[
            float
        ] = []

        annualized_interval_returns: list[
            float
        ] = []

        for previous, current in zip(
            observations[:-1],
            observations[1:],
        ):

            days = (
                current.when
                - previous.when
            ).days

            if days <= 0:
                fail(
                    "non-positive observation interval: "
                    + product_id
                )

            log_return = math.log(
                current.price
                /
                previous.price
            )

            interval_returns.append(
                log_return
            )

            annualized_interval_returns.append(
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
            - latest_previous.when
        ).days

        latest_log_return = math.log(
            latest_current.price
            /
            latest_previous.price
        )

        latest_annualized = (
            latest_log_return
            *
            (
                DAYS_PER_YEAR
                /
                latest_days
            )
        )

        median_annualized = statistics.median(
            annualized_interval_returns
        )

        metrics[
            "latest_interval_days"
        ] = latest_days

        metrics[
            "latest_interval_log_return"
        ] = latest_log_return

        metrics[
            "latest_interval_annualized_log_return"
        ] = latest_annualized

        metrics[
            "median_interval_annualized_log_return"
        ] = median_annualized

        metrics[
            "latest_minus_median_interval_annualized_log_return"
        ] = (
            latest_annualized
            -
            median_annualized
        )

        if (
            len(
                annualized_interval_returns
            )
            >= 2
        ):

            metrics[
                "interval_annualized_log_return_volatility"
            ] = statistics.stdev(
                annualized_interval_returns
            )

        negative = [
            value
            for value
            in annualized_interval_returns
            if value < 0
        ]

        if negative:

            metrics[
                "downside_interval_semideviation"
            ] = math.sqrt(
                statistics.fmean(
                    [
                        value * value
                        for value
                        in negative
                    ]
                )
            )

        metrics[
            "positive_interval_fraction"
        ] = (
            sum(
                1
                for value
                in interval_returns
                if value > 0
            )
            /
            len(
                interval_returns
            )
        )

        metrics[
            "negative_interval_fraction"
        ] = (
            sum(
                1
                for value
                in interval_returns
                if value < 0
            )
            /
            len(
                interval_returns
            )
        )

    own_metrics[
        product_id
    ] = metrics


# ---------------------------------------------------------------------------
# 5. Exact structural peer groups
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
# 6. Product-specific current + peer-relative feature matrix
# ---------------------------------------------------------------------------

output_rows: list[
    dict[str, object]
] = []


current_price_products = 0
current_only_no_history = 0
products_with_exact_peer_current = 0
products_with_exact_peer_history = 0


for product_id in sorted(
    features
):

    feature = features[
        product_id
    ]

    own = own_metrics[
        product_id
    ]

    current_price = parse_positive_float(
        feature.get(
            "tcg_market_price_usd"
        )
    )

    if current_price is not None:
        current_price_products += 1

    observations = history_by_product.get(
        product_id,
        [],
    )

    if (
        current_price is not None
        and not observations
    ):
        current_only_no_history += 1

    peer_ids = [
        peer_id
        for peer_id
        in structural_groups[
            structural_key(
                feature
            )
        ]
        if peer_id != product_id
    ]

    peer_current_prices = []

    peer_history_returns = []

    for peer_id in peer_ids:

        peer_current = parse_positive_float(
            features[
                peer_id
            ].get(
                "tcg_market_price_usd"
            )
        )

        if peer_current is not None:

            peer_current_prices.append(
                peer_current
            )

        peer_return = own_metrics[
            peer_id
        ].get(
            "full_history_annualized_log_return"
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

                peer_history_returns.append(
                    float(
                        peer_return
                    )
                )

    peer_current_median = (
        statistics.median(
            peer_current_prices
        )
        if peer_current_prices
        else None
    )

    peer_history_median = (
        statistics.median(
            peer_history_returns
        )
        if peer_history_returns
        else None
    )

    if peer_current_prices:
        products_with_exact_peer_current += 1

    if peer_history_returns:
        products_with_exact_peer_history += 1

    current_vs_peer_ratio = None
    current_vs_peer_log_discount = None

    if (
        current_price is not None
        and
        peer_current_median is not None
        and
        peer_current_median > 0
    ):

        current_vs_peer_ratio = (
            current_price
            /
            peer_current_median
        )

        current_vs_peer_log_discount = math.log(
            current_price
            /
            peer_current_median
        )

    own_annualized = own.get(
        "full_history_annualized_log_return"
    )

    own_minus_peer_return = None

    if (
        isinstance(
            own_annualized,
            (
                int,
                float,
            )
        )
        and
        peer_history_median is not None
    ):

        own_minus_peer_return = (
            float(
                own_annualized
            )
            -
            peer_history_median
        )

    current_vs_history_median = None
    current_vs_history_high = None
    current_vs_history_low = None
    current_vs_last_history = None

    historical_median = own.get(
        "historical_median_price_usd"
    )

    historical_high = own.get(
        "historical_high_price_usd"
    )

    historical_low = own.get(
        "historical_low_price_usd"
    )

    historical_last = own.get(
        "history_last_price_usd"
    )

    if current_price is not None:

        if isinstance(
            historical_median,
            (
                int,
                float,
            )
        ):

            current_vs_history_median = (
                current_price
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

            current_vs_history_high = (
                current_price
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

            current_vs_history_low = (
                current_price
                /
                float(
                    historical_low
                )
            )

        if isinstance(
            historical_last,
            (
                int,
                float,
            )
        ):

            current_vs_last_history = (
                current_price
                /
                float(
                    historical_last
                )
            ) - 1.0

    row = {
        "secret_lair_id":
            product_id,

        "product_name":
            clean(
                feature.get(
                    "product_name"
                )
            ),

        "tcgplayer_product_id":
            clean(
                feature.get(
                    "tcgplayer_product_id"
                )
            ),

        "current_price_status":
            clean(
                feature.get(
                    "current_price_status"
                )
            ),

        "current_tcg_market_price_usd":
            blank_if_none(
                current_price
            ),

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

        "modeling_method_class_v1":
            clean(
                feature.get(
                    "modeling_method_class"
                )
            ),

        "history_observation_count":
            own[
                "history_observation_count"
            ],

        "history_first_date":
            own[
                "history_first_date"
            ],

        "history_last_date":
            own[
                "history_last_date"
            ],

        "history_span_days":
            own[
                "history_span_days"
            ],

        "history_start_price_usd":
            own[
                "history_start_price_usd"
            ],

        "history_last_price_usd":
            own[
                "history_last_price_usd"
            ],

        "full_history_total_return":
            own[
                "full_history_total_return"
            ],

        "full_history_annualized_log_return":
            own[
                "full_history_annualized_log_return"
            ],

        "full_history_log_price_slope_per_day":
            own[
                "full_history_log_price_slope_per_day"
            ],

        "full_history_log_price_slope_annualized":
            own[
                "full_history_log_price_slope_annualized"
            ],

        "latest_interval_days":
            own[
                "latest_interval_days"
            ],

        "latest_interval_log_return":
            own[
                "latest_interval_log_return"
            ],

        "latest_interval_annualized_log_return":
            own[
                "latest_interval_annualized_log_return"
            ],

        "median_interval_annualized_log_return":
            own[
                "median_interval_annualized_log_return"
            ],

        "latest_minus_median_interval_annualized_log_return":
            own[
                "latest_minus_median_interval_annualized_log_return"
            ],

        "interval_annualized_log_return_volatility":
            own[
                "interval_annualized_log_return_volatility"
            ],

        "downside_interval_semideviation":
            own[
                "downside_interval_semideviation"
            ],

        "maximum_historical_drawdown":
            own[
                "maximum_historical_drawdown"
            ],

        "positive_interval_fraction":
            own[
                "positive_interval_fraction"
            ],

        "negative_interval_fraction":
            own[
                "negative_interval_fraction"
            ],

        "historical_median_price_usd":
            own[
                "historical_median_price_usd"
            ],

        "historical_low_price_usd":
            own[
                "historical_low_price_usd"
            ],

        "historical_high_price_usd":
            own[
                "historical_high_price_usd"
            ],

        "current_vs_last_history_return":
            blank_if_none(
                current_vs_last_history
            ),

        "current_to_historical_median_ratio":
            blank_if_none(
                current_vs_history_median
            ),

        "current_to_historical_high_ratio":
            blank_if_none(
                current_vs_history_high
            ),

        "current_to_historical_low_ratio":
            blank_if_none(
                current_vs_history_low
            ),

        "exact_structural_peer_product_count":
            len(
                peer_ids
            ),

        "exact_peer_current_price_count":
            len(
                peer_current_prices
            ),

        "exact_peer_current_price_median_usd":
            blank_if_none(
                peer_current_median
            ),

        "current_to_exact_peer_median_price_ratio":
            blank_if_none(
                current_vs_peer_ratio
            ),

        "current_vs_exact_peer_median_log_valuation":
            blank_if_none(
                current_vs_peer_log_discount
            ),

        "exact_peer_history_return_count":
            len(
                peer_history_returns
            ),

        "exact_peer_median_full_history_annualized_log_return":
            blank_if_none(
                peer_history_median
            ),

        "own_minus_exact_peer_median_annualized_log_return":
            blank_if_none(
                own_minus_peer_return
            ),

        "release_date_enrichment_available_for_v1_1":
            False,

        "msrp_enrichment_available_for_v1_1":
            False,

        "franchise_ip_enrichment_available_for_v1_1":
            False,

        "artist_theme_enrichment_available_for_v1_1":
            False,

        "forecast_created_in_this_stage":
            False,

        "ranking_created_in_this_stage":
            False,

        "purchase_recommendation_created_in_this_stage":
            False,
    }

    output_rows.append(
        row
    )


if current_price_products != args.expected_current_price_products:

    fail(
        "current-price product population drift: "
        f"expected={args.expected_current_price_products}, "
        f"actual={current_price_products}"
    )


# ---------------------------------------------------------------------------
# 7. Measure feature-vector differentiation.
#
# This is a diagnostic only.
# It does not assign forecasts or rankings.
# ---------------------------------------------------------------------------

signature_fields = (
    "current_tcg_market_price_usd",
    "finish",
    "detailed_finish",
    "product_family",
    "sealed_configuration",
    "history_observation_count",
    "history_span_days",
    "full_history_annualized_log_return",
    "full_history_log_price_slope_annualized",
    "latest_interval_annualized_log_return",
    "latest_minus_median_interval_annualized_log_return",
    "interval_annualized_log_return_volatility",
    "downside_interval_semideviation",
    "maximum_historical_drawdown",
    "current_to_historical_median_ratio",
    "current_to_exact_peer_median_price_ratio",
    "exact_peer_median_full_history_annualized_log_return",
    "own_minus_exact_peer_median_annualized_log_return",
)


def canonical_value(
    value: object,
) -> str:

    if isinstance(
        value,
        float,
    ):

        return (
            f"{value:.12f}"
        )

    return clean(
        value
    )


signatures: dict[
    str,
    list[str],
] = defaultdict(list)


for row in output_rows:

    if not clean(
        row.get(
            "current_tcg_market_price_usd"
        )
    ):
        continue

    signature = "|".join(
        canonical_value(
            row.get(
                field
            )
        )
        for field
        in signature_fields
    )

    signatures[
        signature
    ].append(
        clean(
            row.get(
                "secret_lair_id"
            )
        )
    )


unique_feature_vectors = len(
    signatures
)

products_in_shared_feature_vectors = sum(
    len(
        members
    )
    for members
    in signatures.values()
    if len(
        members
    ) > 1
)

largest_shared_feature_vector = max(
    (
        len(
            members
        )
        for members
        in signatures.values()
    ),
    default=0,
)


if unique_feature_vectors <= 2:

    fail(
        "product-specific feature foundation still collapses "
        "to two or fewer current-price feature vectors"
    )


# ---------------------------------------------------------------------------
# 8. Outputs
# ---------------------------------------------------------------------------

output_path = (
    run_root
    /
    "secret_lair_v1_1_product_feature_foundation.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_1_product_feature_foundation_summary.json"
)


fieldnames = list(
    output_rows[0].keys()
)


write_csv(
    output_path,
    output_rows,
    fieldnames,
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_PRODUCT_FEATURE_FOUNDATION_COMPLETE",

    "source_authority": {
        "history":
            "CERTIFIED_SECRET_LAIR_V1_TCG_HISTORY",

        "existing_v1_feature_matrix":
            True,

        "accepted_history_rows":
            len(
                accepted
            ),
    },

    "snapshot": {
        "products":
            len(
                output_rows
            ),

        "products_with_history":
            len(
                history_by_product
            ),

        "current_price_products":
            current_price_products,

        "current_price_only_no_history_products":
            current_only_no_history,

        "products_with_exact_peer_current_price":
            products_with_exact_peer_current,

        "products_with_exact_peer_history":
            products_with_exact_peer_history,

        "counts_are_permanent_universe_constants":
            False,
    },

    "product_specific_feature_classes": {
        "own_historical_trajectory":
            True,

        "recent_vs_own_history_momentum":
            True,

        "volatility_and_downside":
            True,

        "finish":
            True,

        "product_family_configuration":
            True,

        "exact_structural_peer_performance":
            True,

        "relative_peer_valuation":
            True,

        "ip_theme_msrp_release_enrichment":
            False,
    },

    "differentiation": {
        "unique_current_price_feature_vectors":
            unique_feature_vectors,

        "current_price_products_in_shared_feature_vectors":
            products_in_shared_feature_vectors,

        "largest_shared_feature_vector":
            largest_shared_feature_vector,

        "two_group_forecast_architecture_used":
            False,
    },

    "governance": {
        "forecast_fitted":
            False,

        "v1_forecast_replaced":
            False,

        "v1_ranking_replaced":
            False,

        "v1_purchase_recommendations_replaced":
            False,

        "global_peer_median_used_as_product_forecast":
            False,

        "current_price_used_as_investment_quality_score":
            False,

        "missing_history_imputed":
            False,

        "missing_metadata_imputed":
            False,

        "ebay_used":
            False,

        "automatic_purchase_execution":
            False,
    },

    "next_gate":
        "SL8B_SECRET_LAIR_V1_1_TEMPORAL_PRODUCT_TIME_FEATURE_MATRIX_AND_MODEL_TOURNAMENT",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_V1_1_PRODUCT_FEATURE_FOUNDATION=PASS"
)

print(
    "PRODUCTS="
    + str(
        len(
            output_rows
        )
    )
)

print(
    "PRODUCTS_WITH_HISTORY="
    + str(
        len(
            history_by_product
        )
    )
)

print(
    "CURRENT_PRICE_PRODUCTS="
    + str(
        current_price_products
    )
)

print(
    "CURRENT_PRICE_ONLY_NO_HISTORY_PRODUCTS="
    + str(
        current_only_no_history
    )
)

print(
    "PRODUCTS_WITH_EXACT_PEER_CURRENT_PRICE="
    + str(
        products_with_exact_peer_current
    )
)

print(
    "PRODUCTS_WITH_EXACT_PEER_HISTORY="
    + str(
        products_with_exact_peer_history
    )
)

print(
    "UNIQUE_CURRENT_PRICE_FEATURE_VECTORS="
    + str(
        unique_feature_vectors
    )
)

print(
    "PRODUCTS_IN_SHARED_FEATURE_VECTORS="
    + str(
        products_in_shared_feature_vectors
    )
)

print(
    "LARGEST_SHARED_FEATURE_VECTOR="
    + str(
        largest_shared_feature_vector
    )
)

print(
    "OWN_HISTORY_TRAJECTORY_FEATURES=TRUE"
)

print(
    "RECENT_VS_LONG_TERM_FEATURES=TRUE"
)

print(
    "VOLATILITY_DOWNSIDE_FEATURES=TRUE"
)

print(
    "EXACT_STRUCTURAL_PEER_FEATURES=TRUE"
)

print(
    "RELATIVE_PEER_VALUATION_FEATURES=TRUE"
)

print(
    "FORECAST_CREATED=FALSE"
)

print(
    "V1_BASELINE_REPLACED=FALSE"
)

print(
    "NEXT_GATE=SL8B_SECRET_LAIR_V1_1_TEMPORAL_PRODUCT_TIME_FEATURE_MATRIX_AND_MODEL_TOURNAMENT"
)