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


HORIZON_DAYS = 365

TARGET_METHOD_CLASSES = {
    "SHORT_HISTORY_TOURNAMENT_CANDIDATE",
    "CURRENT_PRICE_ONLY_NEW_PRODUCT_CANDIDATE",
    "CURRENT_AND_HISTORY_EVIDENCE_GAP",
}


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

    return date.fromisoformat(
        text[:10]
    )


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
    origin_date: date
    endpoint_date: date
    elapsed_days: int
    annualized_log_return: float


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

    candidates: list[
        Observation
    ] = []

    for endpoint in observations[
        origin_index + 1:
    ]:

        if endpoint.when <= origin.when:
            continue

        candidates.append(
            endpoint
        )

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda endpoint: (
            abs(
                (
                    endpoint.when
                    - target
                ).days
            ),
            endpoint.when,
        ),
    )


def structural_key(
    feature: dict[str, str],
) -> tuple[str, str, str]:

    return (
        clean(
            feature.get("finish")
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
# Feature snapshot
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
# Reconstruct certified TCG-only historical authority.
# ---------------------------------------------------------------------------

history_rows = read_csv(
    history_path
)

accepted: list[
    Observation
] = []

seen: set[str] = set()

for row in history_rows:

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
            product_id=product_id,
            when=when,
            price=price,
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
        "accepted historical population drift: "
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
# Realized 1Y comparable-return events.
# ---------------------------------------------------------------------------

events_by_product: dict[
    str,
    list[ReturnEvent],
] = defaultdict(list)

all_events: list[
    ReturnEvent
] = []

for (
    product_id,
    observations,
) in history_by_product.items():

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

        elapsed_days = (
            endpoint.when
            - origin.when
        ).days

        if elapsed_days <= 0:
            continue

        annualized_log_return = (
            math.log(
                endpoint.price
                / origin.price
            )
            * (
                float(HORIZON_DAYS)
                / float(
                    elapsed_days
                )
            )
        )

        if not math.isfinite(
            annualized_log_return
        ):
            continue

        event = ReturnEvent(
            product_id=
                product_id,

            origin_date=
                origin.when,

            endpoint_date=
                endpoint.when,

            elapsed_days=
                elapsed_days,

            annualized_log_return=
                annualized_log_return,
        )

        events_by_product[
            product_id
        ].append(event)

        all_events.append(event)


if not all_events:
    fail(
        "zero realized comparable events"
    )


# ---------------------------------------------------------------------------
# Product-level comparable evidence.
#
# No arbitrary top-N selection.
# Every eligible historical peer product is preserved.
# ---------------------------------------------------------------------------

peer_product_stats: dict[
    str,
    dict[str, object],
] = {}

for (
    product_id,
    events,
) in events_by_product.items():

    returns = [
        event.annualized_log_return
        for event in events
    ]

    peer_product_stats[
        product_id
    ] = {
        "event_count":
            len(events),

        "median_annualized_log_return":
            statistics.median(
                returns
            ),

        "return_dispersion":
            (
                statistics.pstdev(
                    returns
                )
                if len(returns) > 1
                else 0.0
            ),

        "latest_realized_endpoint":
            max(
                event.endpoint_date
                for event in events
            ),
    }


target_rows = [
    row
    for row in feature_rows
    if clean(
        row.get(
            "modeling_method_class"
        )
    )
    in TARGET_METHOD_CLASSES
]

if not target_rows:
    fail(
        "no short/no-history targets found"
    )


edge_rows: list[
    dict[str, object]
] = []

summary_rows: list[
    dict[str, object]
] = []


for target in sorted(
    target_rows,
    key=lambda row:
        clean(
            row.get(
                "secret_lair_id"
            )
        ),
):

    target_id = clean(
        target.get(
            "secret_lair_id"
        )
    )

    target_key = structural_key(
        target
    )

    target_method = clean(
        target.get(
            "modeling_method_class"
        )
    )

    current_price = (
        parse_positive_float(
            target.get(
                "tcg_market_price_usd"
            )
        )
    )

    global_peer_ids: list[str] = []

    exact_peer_ids: list[str] = []

    global_event_returns: list[
        float
    ] = []

    exact_event_returns: list[
        float
    ] = []

    for peer_id in sorted(
        peer_product_stats.keys()
    ):

        # Mandatory target holdout.
        if peer_id == target_id:
            continue

        peer_feature = features.get(
            peer_id
        )

        if peer_feature is None:
            continue

        peer_stats = peer_product_stats[
            peer_id
        ]

        peer_events = events_by_product[
            peer_id
        ]

        is_exact = (
            structural_key(
                peer_feature
            )
            == target_key
        )

        global_peer_ids.append(
            peer_id
        )

        global_event_returns.extend(
            event.annualized_log_return
            for event
            in peer_events
        )

        if is_exact:

            exact_peer_ids.append(
                peer_id
            )

            exact_event_returns.extend(
                event.annualized_log_return
                for event
                in peer_events
            )

        edge_rows.append(
            {
                "target_secret_lair_id":
                    target_id,

                "target_product_name":
                    clean(
                        target.get(
                            "product_name"
                        )
                    ),

                "target_method_class":
                    target_method,

                "comparable_secret_lair_id":
                    peer_id,

                "comparable_product_name":
                    clean(
                        peer_feature.get(
                            "product_name"
                        )
                    ),

                "target_finish":
                    clean(
                        target.get(
                            "finish"
                        )
                    ),

                "comparable_finish":
                    clean(
                        peer_feature.get(
                            "finish"
                        )
                    ),

                "target_product_family":
                    clean(
                        target.get(
                            "product_family"
                        )
                    ),

                "comparable_product_family":
                    clean(
                        peer_feature.get(
                            "product_family"
                        )
                    ),

                "target_sealed_configuration":
                    clean(
                        target.get(
                            "sealed_configuration"
                        )
                    ),

                "comparable_sealed_configuration":
                    clean(
                        peer_feature.get(
                            "sealed_configuration"
                        )
                    ),

                "exact_structural_match":
                    is_exact,

                "broad_global_peer_eligible":
                    True,

                "comparable_realized_1y_event_count":
                    int(
                        peer_stats[
                            "event_count"
                        ]
                    ),

                "comparable_median_annualized_log_return":
                    peer_stats[
                        "median_annualized_log_return"
                    ],

                "comparable_return_dispersion":
                    peer_stats[
                        "return_dispersion"
                    ],

                "comparable_latest_realized_endpoint":
                    peer_stats[
                        "latest_realized_endpoint"
                    ].isoformat(),

                "target_excluded_from_own_comparables":
                    True,

                "arbitrary_top_n_selection_used":
                    False,
            }
        )


    if not global_peer_ids:
        comparable_class = (
            "NO_REALIZED_COMPARABLE_EVIDENCE"
        )

    elif exact_peer_ids:
        comparable_class = (
            "EXACT_STRUCTURAL_AND_GLOBAL_COMPARABLES_AVAILABLE"
        )

    else:
        comparable_class = (
            "GLOBAL_COMPARABLES_AVAILABLE_ONLY"
        )


    if current_price is None:

        forecast_anchor_status = (
            "NO_GOVERNED_CURRENT_PRICE_ANCHOR"
        )

        dollar_forecast_allowed = False

    else:

        forecast_anchor_status = (
            "GOVERNED_TCG_CURRENT_PRICE_ANCHOR_AVAILABLE"
        )

        dollar_forecast_allowed = (
            len(global_peer_ids) > 0
        )


    global_median = (
        statistics.median(
            global_event_returns
        )
        if global_event_returns
        else None
    )

    exact_median = (
        statistics.median(
            exact_event_returns
        )
        if exact_event_returns
        else None
    )

    global_dispersion = (
        statistics.pstdev(
            global_event_returns
        )
        if len(
            global_event_returns
        ) > 1
        else (
            0.0
            if global_event_returns
            else None
        )
    )

    exact_dispersion = (
        statistics.pstdev(
            exact_event_returns
        )
        if len(
            exact_event_returns
        ) > 1
        else (
            0.0
            if exact_event_returns
            else None
        )
    )


    summary_rows.append(
        {
            "secret_lair_id":
                target_id,

            "product_name":
                clean(
                    target.get(
                        "product_name"
                    )
                ),

            "modeling_method_class":
                target_method,

            "current_price_available":
                current_price
                is not None,

            "target_finish":
                clean(
                    target.get(
                        "finish"
                    )
                ),

            "target_product_family":
                clean(
                    target.get(
                        "product_family"
                    )
                ),

            "target_sealed_configuration":
                clean(
                    target.get(
                        "sealed_configuration"
                    )
                ),

            "exact_structural_comparable_product_count":
                len(
                    exact_peer_ids
                ),

            "global_comparable_product_count":
                len(
                    global_peer_ids
                ),

            "exact_structural_comparable_event_count":
                len(
                    exact_event_returns
                ),

            "global_comparable_event_count":
                len(
                    global_event_returns
                ),

            "exact_structural_comparable_ids":
                "|".join(
                    exact_peer_ids
                ),

            "global_comparable_ids":
                "|".join(
                    global_peer_ids
                ),

            "exact_structural_median_annualized_log_return":
                (
                    ""
                    if exact_median
                    is None
                    else exact_median
                ),

            "global_median_annualized_log_return":
                (
                    ""
                    if global_median
                    is None
                    else global_median
                ),

            "exact_structural_return_dispersion":
                (
                    ""
                    if exact_dispersion
                    is None
                    else exact_dispersion
                ),

            "global_return_dispersion":
                (
                    ""
                    if global_dispersion
                    is None
                    else global_dispersion
                ),

            "comparable_evidence_class":
                comparable_class,

            "forecast_anchor_status":
                forecast_anchor_status,

            "comparable_supported_dollar_forecast_possible":
                dollar_forecast_allowed,

            "target_excluded_from_own_comparables":
                True,

            "arbitrary_minimum_comparable_count_used":
                False,

            "arbitrary_top_n_comparable_selection_used":
                False,

            "production_forecast_authorized":
                False,
        }
    )


# ---------------------------------------------------------------------------
# Required no-history coverage.
# ---------------------------------------------------------------------------

no_history_rows = [
    row
    for row in summary_rows
    if row[
        "modeling_method_class"
    ]
    in (
        "CURRENT_PRICE_ONLY_NEW_PRODUCT_CANDIDATE",
        "CURRENT_AND_HISTORY_EVIDENCE_GAP",
    )
]

no_history_without_global = [
    row
    for row in no_history_rows
    if int(
        row[
            "global_comparable_product_count"
        ]
    ) == 0
]

if no_history_without_global:
    fail(
        "one or more no-history products have zero "
        "realized comparable products"
    )


current_only_rows = [
    row
    for row in summary_rows
    if row[
        "modeling_method_class"
    ]
    ==
    "CURRENT_PRICE_ONLY_NEW_PRODUCT_CANDIDATE"
]

current_only_not_forecastable = [
    row
    for row in current_only_rows
    if not bool(
        row[
            "comparable_supported_dollar_forecast_possible"
        ]
    )
]

if current_only_not_forecastable:
    fail(
        "one or more current-price-only products "
        "lack comparable-supported forecast capability"
    )


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

edge_path = (
    run_root
    / "secret_lair_v1_comparable_edge_ledger.csv"
)

summary_path = (
    run_root
    / "secret_lair_v1_comparable_target_summary.csv"
)

json_path = (
    run_root
    / "secret_lair_v1_comparable_evidence_summary.json"
)


write_csv(
    edge_path,
    edge_rows,
    [
        "target_secret_lair_id",
        "target_product_name",
        "target_method_class",
        "comparable_secret_lair_id",
        "comparable_product_name",
        "target_finish",
        "comparable_finish",
        "target_product_family",
        "comparable_product_family",
        "target_sealed_configuration",
        "comparable_sealed_configuration",
        "exact_structural_match",
        "broad_global_peer_eligible",
        "comparable_realized_1y_event_count",
        "comparable_median_annualized_log_return",
        "comparable_return_dispersion",
        "comparable_latest_realized_endpoint",
        "target_excluded_from_own_comparables",
        "arbitrary_top_n_selection_used",
    ],
)


write_csv(
    summary_path,
    summary_rows,
    [
        "secret_lair_id",
        "product_name",
        "modeling_method_class",
        "current_price_available",
        "target_finish",
        "target_product_family",
        "target_sealed_configuration",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "exact_structural_comparable_event_count",
        "global_comparable_event_count",
        "exact_structural_comparable_ids",
        "global_comparable_ids",
        "exact_structural_median_annualized_log_return",
        "global_median_annualized_log_return",
        "exact_structural_return_dispersion",
        "global_return_dispersion",
        "comparable_evidence_class",
        "forecast_anchor_status",
        "comparable_supported_dollar_forecast_possible",
        "target_excluded_from_own_comparables",
        "arbitrary_minimum_comparable_count_used",
        "arbitrary_top_n_comparable_selection_used",
        "production_forecast_authorized",
    ],
)


exact_available = [
    row
    for row in summary_rows
    if int(
        row[
            "exact_structural_comparable_product_count"
        ]
    ) > 0
]

global_only = [
    row
    for row in summary_rows
    if (
        int(
            row[
                "exact_structural_comparable_product_count"
            ]
        ) == 0
        and
        int(
            row[
                "global_comparable_product_count"
            ]
        ) > 0
    )
]

short_history = [
    row
    for row in summary_rows
    if row[
        "modeling_method_class"
    ]
    ==
    "SHORT_HISTORY_TOURNAMENT_CANDIDATE"
]

evidence_gap = [
    row
    for row in summary_rows
    if row[
        "modeling_method_class"
    ]
    ==
    "CURRENT_AND_HISTORY_EVIDENCE_GAP"
]


payload = {
    "status":
        "SECRET_LAIR_V1_COMPARABLE_EVIDENCE_ASSIGNMENT_COMPLETE",

    "target_products":
        len(summary_rows),

    "short_history_targets":
        len(short_history),

    "current_price_only_targets":
        len(current_only_rows),

    "no_history_no_current_price_targets":
        len(evidence_gap),

    "no_history_targets":
        len(no_history_rows),

    "no_history_targets_with_global_comparables":
        sum(
            1
            for row
            in no_history_rows
            if int(
                row[
                    "global_comparable_product_count"
                ]
            ) > 0
        ),

    "current_price_only_targets_with_comparable_supported_dollar_forecast":
        sum(
            1
            for row
            in current_only_rows
            if bool(
                row[
                    "comparable_supported_dollar_forecast_possible"
                ]
            )
        ),

    "targets_with_exact_structural_comparables":
        len(exact_available),

    "targets_requiring_global_only_comparable_evidence":
        len(global_only),

    "realized_1y_return_events":
        len(all_events),

    "historical_peer_products_with_realized_1y_events":
        len(
            peer_product_stats
        ),

    "comparable_edge_rows":
        len(edge_rows),

    "exact_structural_dimensions": [
        "finish",
        "product_family",
        "sealed_configuration",
    ],

    "selection": {
        "arbitrary_minimum_comparable_count":
            False,

        "arbitrary_top_n":
            False,

        "all_eligible_peer_ids_persisted":
            True,

        "target_product_holdout":
            True,
    },

    "forecast_authority": {
        "production_method_certified":
            False,

        "production_forecast":
            False,

        "ranking":
            False,

        "purchase_recommendation":
            False,
    },
}


json_path.write_text(
    json.dumps(
        payload,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_COMPARABLE_EVIDENCE=PASS"
)

print(
    "TARGET_PRODUCTS="
    + str(
        len(summary_rows)
    )
)

print(
    "SHORT_HISTORY_TARGETS="
    + str(
        len(short_history)
    )
)

print(
    "CURRENT_PRICE_ONLY_TARGETS="
    + str(
        len(current_only_rows)
    )
)

print(
    "NO_HISTORY_NO_CURRENT_PRICE_TARGETS="
    + str(
        len(evidence_gap)
    )
)

print(
    "NO_HISTORY_TARGETS="
    + str(
        len(no_history_rows)
    )
)

print(
    "NO_HISTORY_WITH_GLOBAL_COMPARABLES="
    + str(
        payload[
            "no_history_targets_with_global_comparables"
        ]
    )
)

print(
    "CURRENT_PRICE_ONLY_WITH_COMPARABLE_SUPPORTED_DOLLAR_FORECAST="
    + str(
        payload[
            "current_price_only_targets_with_comparable_supported_dollar_forecast"
        ]
    )
)

print(
    "TARGETS_WITH_EXACT_STRUCTURAL_COMPARABLES="
    + str(
        len(exact_available)
    )
)

print(
    "TARGETS_GLOBAL_ONLY="
    + str(
        len(global_only)
    )
)

print(
    "HISTORICAL_PEER_PRODUCTS="
    + str(
        len(peer_product_stats)
    )
)

print(
    "REALIZED_1Y_RETURN_EVENTS="
    + str(
        len(all_events)
    )
)

print(
    "COMPARABLE_EDGE_ROWS="
    + str(
        len(edge_rows)
    )
)

print(
    "ARBITRARY_MINIMUM_COMPARABLE_COUNT=FALSE"
)

print(
    "ARBITRARY_TOP_N_COMPARABLE_SELECTION=FALSE"
)

print(
    "TARGET_PRODUCT_HOLDOUT=TRUE"
)

print(
    "PRODUCTION_FORECAST_AUTHORIZED=FALSE"
)