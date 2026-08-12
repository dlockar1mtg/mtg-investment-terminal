from __future__ import annotations

import argparse
import csv
import json
import math

from collections import defaultdict
from pathlib import Path


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_float(
    value: object,
    *,
    allow_blank: bool = False,
) -> float | None:

    text = clean(value)

    if not text:

        if allow_blank:
            return None

        fail(
            "required numeric field is blank"
        )

    try:
        result = float(text)
    except ValueError:
        fail(
            "invalid numeric value: "
            + text
        )

    if not math.isfinite(result):
        fail(
            "non-finite numeric value"
        )

    return result


def parse_int(
    value: object,
) -> int:

    text = clean(value)

    if not text:
        return 0

    try:
        return int(
            float(text)
        )
    except ValueError:
        fail(
            "invalid integer value: "
            + text
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
    "--architecture",
    required=True,
)

parser.add_argument(
    "--forecasts",
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
    "--expected-products",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-signatures",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-tied-products",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-largest-tie",
    required=True,
    type=int,
)

args = parser.parse_args()

architecture_rows = read_csv(
    Path(
        args.architecture
    )
)

forecast_rows = read_csv(
    Path(
        args.forecasts
    )
)

risk_rows = read_csv(
    Path(
        args.risk
    )
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


if (
    len(architecture_rows)
    != args.expected_products
):
    fail(
        "ranking architecture population drift: "
        f"expected={args.expected_products}, "
        f"actual={len(architecture_rows)}"
    )


# ---------------------------------------------------------------------------
# Forecast lookup
# ---------------------------------------------------------------------------

forecasts: dict[
    str,
    dict[str, str],
] = {}

for row in forecast_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank forecast product ID"
        )

    if product_id in forecasts:
        fail(
            "duplicate forecast product ID: "
            + product_id
        )

    forecasts[
        product_id
    ] = row


# ---------------------------------------------------------------------------
# Risk lookup
# ---------------------------------------------------------------------------

risk: dict[
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

    if horizon in risk[
        product_id
    ]:
        fail(
            "duplicate risk product/horizon: "
            + product_id
            + " "
            + horizon
        )

    risk[
        product_id
    ][
        horizon
    ] = row


# ---------------------------------------------------------------------------
# Convert governed architecture to rank groups.
#
# IMPORTANT:
#
# Group order is determined ONLY from:
#
#   primary:
#       central_1y_log_return
#
#   inside identical underlying return profile:
#       own history ordinal
#       exact comparable support ordinal
#       history span
#       observation count
#       exact comparable event count
#       global comparable event count
#
# The final tie signature determines equality.
# ---------------------------------------------------------------------------

signature_rows: dict[
    str,
    list[
        dict[str, str]
    ],
] = defaultdict(list)


for row in architecture_rows:

    signature = clean(
        row.get(
            "full_ranking_tie_signature"
        )
    )

    if not signature:
        fail(
            "missing full ranking tie signature"
        )

    signature_rows[
        signature
    ].append(
        row
    )


if (
    len(signature_rows)
    != args.expected_signatures
):
    fail(
        "ranking-signature count drift: "
        f"expected={args.expected_signatures}, "
        f"actual={len(signature_rows)}"
    )


group_records: list[
    dict[str, object]
] = []


# ---------------------------------------------------------------------------
# Ensure the current snapshot has no ambiguous equal-return / different-profile
# case. The certified architecture only permits the evidence hierarchy INSIDE
# an identical underlying return profile.
#
# If a future refresh creates equal primary return across different profiles,
# ranking must be re-audited rather than silently inventing an ordering.
# ---------------------------------------------------------------------------

return_to_profiles: dict[
    str,
    set[str],
] = defaultdict(set)


for row in architecture_rows:

    central_return = parse_float(
        row.get(
            "central_1y_log_return"
        )
    )

    return_key = (
        f"{central_return:.12f}"
    )

    profile = clean(
        row.get(
            "underlying_return_profile"
        )
    )

    return_to_profiles[
        return_key
    ].add(
        profile
    )


ambiguous_primary = {
    key:
        profiles
    for key, profiles
    in return_to_profiles.items()
    if len(profiles) > 1
}


if ambiguous_primary:
    fail(
        "equal primary modeled return exists across different "
        "underlying return profiles; ranking architecture must "
        "be re-audited before ordering"
    )


for (
    signature,
    members,
) in signature_rows.items():

    exemplar = members[0]

    # Verify every row in the signature has exactly the same rank tuple.

    primary_return_raw = parse_float(
        exemplar.get(
            "central_1y_log_return"
        )
    )

    # Canonical ranking precision is inherited from the CERTIFIED SL-6A.2
    # underlying-return signature, which was built at 12 decimal places.
    #
    # This is not a new tolerance or ranking threshold.
    primary_return_key = (
        f"{primary_return_raw:.12f}"
    )

    primary_return = float(
        primary_return_key
    )

    profile = clean(
        exemplar.get(
            "underlying_return_profile"
        )
    )

    own_history_ordinal = parse_int(
        exemplar.get(
            "own_history_ordinal_for_lexicographic_sort_only"
        )
    )

    exact_support_ordinal = parse_int(
        exemplar.get(
            "exact_support_ordinal_for_lexicographic_sort_only"
        )
    )

    history_span = parse_int(
        exemplar.get(
            "history_span_days"
        )
    )

    historical_observations = parse_int(
        exemplar.get(
            "historical_observation_count"
        )
    )

    exact_events = parse_int(
        exemplar.get(
            "exact_structural_comparable_event_count"
        )
    )

    global_events = parse_int(
        exemplar.get(
            "global_comparable_event_count"
        )
    )


    expected_tuple = (
        primary_return_key,
        profile,
        own_history_ordinal,
        exact_support_ordinal,
        history_span,
        historical_observations,
        exact_events,
        global_events,
    )


    for member in members:

        member_primary_return_raw = parse_float(
            member.get(
                "central_1y_log_return"
            )
        )

        member_primary_return_key = (
            f"{member_primary_return_raw:.12f}"
        )

        member_tuple = (
            member_primary_return_key,

            clean(
                member.get(
                    "underlying_return_profile"
                )
            ),

            parse_int(
                member.get(
                    "own_history_ordinal_for_lexicographic_sort_only"
                )
            ),

            parse_int(
                member.get(
                    "exact_support_ordinal_for_lexicographic_sort_only"
                )
            ),

            parse_int(
                member.get(
                    "history_span_days"
                )
            ),

            parse_int(
                member.get(
                    "historical_observation_count"
                )
            ),

            parse_int(
                member.get(
                    "exact_structural_comparable_event_count"
                )
            ),

            parse_int(
                member.get(
                    "global_comparable_event_count"
                )
            ),
        )

        if member_tuple != expected_tuple:
            fail(
                "full tie signature contains differing rank tuples: "
                + signature
            )


    group_records.append(
        {
            "signature":
                signature,

            "members":
                members,

            "primary_return":
                primary_return,

            "profile":
                profile,

            "own_history_ordinal":
                own_history_ordinal,

            "exact_support_ordinal":
                exact_support_ordinal,

            "history_span":
                history_span,

            "historical_observations":
                historical_observations,

            "exact_events":
                exact_events,

            "global_events":
                global_events,
        }
    )


# ---------------------------------------------------------------------------
# Higher is better for every governed rank dimension.
#
# This lexicographic key is NOT a weighted score.
# ---------------------------------------------------------------------------

group_records.sort(
    key=lambda group: (
        -float(
            group[
                "primary_return"
            ]
        ),
        -int(
            group[
                "own_history_ordinal"
            ]
        ),
        -int(
            group[
                "exact_support_ordinal"
            ]
        ),
        -int(
            group[
                "history_span"
            ]
        ),
        -int(
            group[
                "historical_observations"
            ]
        ),
        -int(
            group[
                "exact_events"
            ]
        ),
        -int(
            group[
                "global_events"
            ]
        ),
    )
)


# ---------------------------------------------------------------------------
# Competition ranks.
#
# Example:
#
#   group size 3 at rank 1  -> ranks 1,1,1
#   next group starts rank 4
#
# No ID/name order affects the competition rank.
# ---------------------------------------------------------------------------

ranking_rows: list[
    dict[str, object]
] = []

competition_position = 1
rank_group_index = 0

tied_products = 0
largest_tie = 0


for group in group_records:

    rank_group_index += 1

    members = list(
        group[
            "members"
        ]
    )

    group_size = len(
        members
    )

    competition_rank = (
        competition_position
    )

    largest_tie = max(
        largest_tie,
        group_size,
    )

    if group_size > 1:
        tied_products += group_size


    # Input-row serialization order only.
    #
    # This is NOT a rank tie-break. Every member receives the exact same
    # competition_rank and rank_group_index.

    for member in members:

        product_id = clean(
            member.get(
                "secret_lair_id"
            )
        )

        forecast = forecasts.get(
            product_id
        )

        if forecast is None:
            fail(
                "rank product missing production forecast: "
                + product_id
            )

        if (
            clean(
                forecast.get(
                    "forecast_status"
                )
            )
            !=
            "PRODUCTION_1Y_FORECAST"
        ):
            fail(
                "ranking contains non-production forecast product: "
                + product_id
            )

        horizons = risk.get(
            product_id,
            {}
        )

        if set(
            horizons.keys()
        ) != {
            "Y1",
            "Y3",
            "Y5",
        }:
            fail(
                "ranking product missing Y1/Y3/Y5 risk evidence: "
                + product_id
            )

        y1 = horizons[
            "Y1"
        ]

        y3 = horizons[
            "Y3"
        ]

        y5 = horizons[
            "Y5"
        ]


        current_price = parse_float(
            forecast.get(
                "current_tcg_market_price_usd"
            )
        )

        point_forecast = parse_float(
            forecast.get(
                "one_year_forecast_usd"
            )
        )

        point_return = (
            point_forecast
            /
            current_price
        ) - 1.0


        ranking_rows.append(
            {
                "competition_rank":
                    competition_rank,

                "rank_group_index":
                    rank_group_index,

                "rank_group_size":
                    group_size,

                "co_ranked_tie":
                    group_size > 1,

                "secret_lair_id":
                    product_id,

                "product_name":
                    clean(
                        member.get(
                            "product_name"
                        )
                    ),

                "production_method":
                    clean(
                        member.get(
                            "production_method"
                        )
                    ),

                "modeling_method_class":
                    clean(
                        member.get(
                            "modeling_method_class"
                        )
                    ),

                "central_1y_log_return":
                    group[
                        "primary_return"
                    ],

                "certified_1y_point_return":
                    point_return,

                "current_tcg_market_price_usd":
                    current_price,

                "certified_1y_point_forecast_usd":
                    point_forecast,

                "own_history_evidence_class":
                    clean(
                        member.get(
                            "own_history_evidence_class"
                        )
                    ),

                "exact_structural_comparable_support":
                    clean(
                        member.get(
                            "exact_structural_comparable_support"
                        )
                    ),

                "history_span_days":
                    group[
                        "history_span"
                    ],

                "historical_observation_count":
                    group[
                        "historical_observations"
                    ],

                "exact_structural_comparable_product_count":
                    parse_int(
                        member.get(
                            "exact_structural_comparable_product_count"
                        )
                    ),

                "global_comparable_product_count":
                    parse_int(
                        member.get(
                            "global_comparable_product_count"
                        )
                    ),

                "exact_structural_comparable_event_count":
                    group[
                        "exact_events"
                    ],

                "global_comparable_event_count":
                    group[
                        "global_events"
                    ],

                "y1_probability_of_loss":
                    parse_float(
                        y1.get(
                            "probability_of_loss"
                        )
                    ),

                "y1_probability_of_positive_return":
                    parse_float(
                        y1.get(
                            "probability_of_positive_return"
                        )
                    ),

                "y1_q10_terminal_value_usd":
                    parse_float(
                        y1.get(
                            "q10_terminal_value_usd"
                        )
                    ),

                "y1_q50_terminal_value_usd":
                    parse_float(
                        y1.get(
                            "q50_terminal_value_usd"
                        )
                    ),

                "y1_q90_terminal_value_usd":
                    parse_float(
                        y1.get(
                            "q90_terminal_value_usd"
                        )
                    ),

                "y1_downside_tail_mean_total_return":
                    parse_float(
                        y1.get(
                            "downside_tail_mean_total_return"
                        )
                    ),

                "y1_upside_tail_mean_total_return":
                    parse_float(
                        y1.get(
                            "upside_tail_mean_total_return"
                        )
                    ),

                "y3_median_total_return_scenario":
                    parse_float(
                        y3.get(
                            "median_total_return"
                        )
                    ),

                "y3_probability_of_loss_scenario":
                    parse_float(
                        y3.get(
                            "probability_of_loss"
                        )
                    ),

                "y5_median_total_return_scenario":
                    parse_float(
                        y5.get(
                            "median_total_return"
                        )
                    ),

                "y5_probability_of_loss_scenario":
                    parse_float(
                        y5.get(
                            "probability_of_loss"
                        )
                    ),

                "underlying_return_profile":
                    group[
                        "profile"
                    ],

                "full_ranking_tie_signature":
                    group[
                        "signature"
                    ],

                "ranking_primary_signal":
                    "CERTIFIED_CENTRAL_1Y_MODELED_RETURN",

                "ranking_secondary_method":
                    "LEXICOGRAPHIC_GOVERNED_EVIDENCE_HIERARCHY",

                "risk_metrics_used_to_break_identical_profile_ties":
                    False,

                "monte_carlo_seed_used_for_rank":
                    False,

                "current_price_used_for_rank":
                    False,

                "product_id_used_for_rank":
                    False,

                "product_name_used_for_rank":
                    False,

                "weighted_ranking_score_used":
                    False,

                "purchase_analysis_authorized":
                    False,

                "purchase_recommendation_authorized":
                    False,

                "row_order_inside_tie_has_rank_meaning":
                    False,
            }
        )


    competition_position += (
        group_size
    )


if len(
    ranking_rows
) != args.expected_products:
    fail(
        "ranked product count mismatch"
    )


if (
    len(
        group_records
    )
    !=
    args.expected_signatures
):
    fail(
        "rank group count mismatch"
    )


if tied_products != args.expected_tied_products:
    fail(
        "genuine tie product count drift: "
        f"expected={args.expected_tied_products}, "
        f"actual={tied_products}"
    )


if largest_tie != args.expected_largest_tie:
    fail(
        "largest genuine tie drift: "
        f"expected={args.expected_largest_tie}, "
        f"actual={largest_tie}"
    )


# ---------------------------------------------------------------------------
# Validate all members of each tie signature received the same competition
# rank and no signature received multiple ranks.
# ---------------------------------------------------------------------------

signature_ranks: dict[
    str,
    set[int],
] = defaultdict(set)

for row in ranking_rows:

    signature_ranks[
        str(
            row[
                "full_ranking_tie_signature"
            ]
        )
    ].add(
        int(
            row[
                "competition_rank"
            ]
        )
    )


for signature, ranks in (
    signature_ranks.items()
):

    if len(ranks) != 1:
        fail(
            "tie signature received multiple competition ranks: "
            + signature
        )


# ---------------------------------------------------------------------------
# Validate monotonic primary ordering.
# ---------------------------------------------------------------------------

previous_primary: float | None = None

for group in group_records:

    current_primary = float(
        group[
            "primary_return"
        ]
    )

    if (
        previous_primary is not None
        and
        current_primary >
        previous_primary
    ):
        fail(
            "primary modeled return ordering is not descending"
        )

    previous_primary = (
        current_primary
    )


ranking_path = (
    run_root
    /
    "secret_lair_v1_investment_ranking.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_investment_ranking_summary.json"
)


write_csv(
    ranking_path,
    ranking_rows,
    [
        "competition_rank",
        "rank_group_index",
        "rank_group_size",
        "co_ranked_tie",
        "secret_lair_id",
        "product_name",
        "production_method",
        "modeling_method_class",
        "central_1y_log_return",
        "certified_1y_point_return",
        "current_tcg_market_price_usd",
        "certified_1y_point_forecast_usd",
        "own_history_evidence_class",
        "exact_structural_comparable_support",
        "history_span_days",
        "historical_observation_count",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "exact_structural_comparable_event_count",
        "global_comparable_event_count",
        "y1_probability_of_loss",
        "y1_probability_of_positive_return",
        "y1_q10_terminal_value_usd",
        "y1_q50_terminal_value_usd",
        "y1_q90_terminal_value_usd",
        "y1_downside_tail_mean_total_return",
        "y1_upside_tail_mean_total_return",
        "y3_median_total_return_scenario",
        "y3_probability_of_loss_scenario",
        "y5_median_total_return_scenario",
        "y5_probability_of_loss_scenario",
        "underlying_return_profile",
        "full_ranking_tie_signature",
        "ranking_primary_signal",
        "ranking_secondary_method",
        "risk_metrics_used_to_break_identical_profile_ties",
        "monte_carlo_seed_used_for_rank",
        "current_price_used_for_rank",
        "product_id_used_for_rank",
        "product_name_used_for_rank",
        "weighted_ranking_score_used",
        "purchase_analysis_authorized",
        "purchase_recommendation_authorized",
        "row_order_inside_tie_has_rank_meaning",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_INVESTMENT_RANKING_EXECUTION_COMPLETE",

    "ranked_products":
        len(
            ranking_rows
        ),

    "rank_groups":
        len(
            group_records
        ),

    "competition_ranking":
        True,

    "products_in_genuine_ties":
        tied_products,

    "largest_genuine_tie":
        largest_tie,

    "highest_competition_rank":
        max(
            int(
                row[
                    "competition_rank"
                ]
            )
            for row
            in ranking_rows
        ),

    "ranking_rule": {
        "primary":
            "CERTIFIED_CENTRAL_1Y_MODELED_RETURN_DESC",

        "primary_canonical_precision_decimal_places":
            12,

        "primary_precision_source":
            "CERTIFIED_SL6A2_UNDERLYING_RETURN_PROFILE_SIGNATURE",

        "secondary_scope":
            "ONLY_INSIDE_IDENTICAL_UNDERLYING_RETURN_PROFILE",

        "secondary":
            [
                "OWN_HISTORY_EVIDENCE_CLASS_DESC",
                "EXACT_STRUCTURAL_COMPARABLE_SUPPORT_DESC",
                "HISTORY_SPAN_DAYS_DESC",
                "HISTORICAL_OBSERVATION_COUNT_DESC",
                "EXACT_STRUCTURAL_COMPARABLE_EVENT_COUNT_DESC",
                "GLOBAL_COMPARABLE_EVENT_COUNT_DESC",
            ],

        "remaining_identical_tuple":
            "CO_RANKED_COMPETITION_TIE",

        "weighted_score":
            False,

        "risk_metric_tie_break":
            False,

        "monte_carlo_seed_tie_break":
            False,

        "current_price_tie_break":
            False,

        "product_id_tie_break":
            False,

        "product_name_tie_break":
            False,
    },

    "authority": {
        "ranking":
            True,

        "purchase_analysis_execution":
            True,

        "purchase_analysis_certified":
            False,

        "purchase_recommendation":
            False,

        "automatic_purchase_execution":
            False,
    },

    "next_gate":
        "SL6C_SECRET_LAIR_PURCHASE_ANALYSIS",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_INVESTMENT_RANKING=PASS"
)

print(
    "RANKED_PRODUCTS="
    + str(
        len(
            ranking_rows
        )
    )
)

print(
    "RANK_GROUPS="
    + str(
        len(
            group_records
        )
    )
)

print(
    "COMPETITION_RANKING=TRUE"
)

print(
    "PRODUCTS_IN_GENUINE_TIES="
    + str(
        tied_products
    )
)

print(
    "LARGEST_GENUINE_TIE="
    + str(
        largest_tie
    )
)

print(
    "MONTE_CARLO_SEED_TIE_BREAK=FALSE"
)

print(
    "RISK_METRIC_TIE_BREAK=FALSE"
)

print(
    "CURRENT_PRICE_TIE_BREAK=FALSE"
)

print(
    "PRODUCT_ID_TIE_BREAK=FALSE"
)

print(
    "WEIGHTED_RANKING_SCORE=FALSE"
)

print(
    "RANKING_CERTIFIED=TRUE"
)

print(
    "PURCHASE_ANALYSIS_EXECUTION_AUTHORIZED=TRUE"
)

print(
    "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
)

print(
    "NEXT_GATE=SL6C_SECRET_LAIR_PURCHASE_ANALYSIS"
)