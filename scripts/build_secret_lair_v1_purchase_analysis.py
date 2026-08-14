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
) -> float:

    text = clean(value)

    if not text:
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


def relative_margin(
    terminal_value: float,
    current_price: float,
) -> float:

    return (
        terminal_value
        /
        current_price
    ) - 1.0


def factual_price_state(
    current_price: float,
    terminal_value: float,
) -> str:

    if current_price < terminal_value:
        return "CURRENT_PRICE_BELOW_BREAK_EVEN_LEVEL"

    if current_price > terminal_value:
        return "CURRENT_PRICE_ABOVE_BREAK_EVEN_LEVEL"

    return "CURRENT_PRICE_EQUALS_BREAK_EVEN_LEVEL"


parser = argparse.ArgumentParser()

parser.add_argument(
    "--ranking",
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
    "--expected-rank-groups",
    required=True,
    type=int,
)

args = parser.parse_args()


ranking_rows = read_csv(
    Path(
        args.ranking
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


if len(ranking_rows) != args.expected_products:
    fail(
        "purchase-analysis ranking population drift: "
        f"expected={args.expected_products}, "
        f"actual={len(ranking_rows)}"
    )


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

    if not product_id:
        fail(
            "blank risk product ID"
        )

    if horizon not in {
        "Y1",
        "Y3",
        "Y5",
    }:
        continue

    if horizon in risk[
        product_id
    ]:
        fail(
            "duplicate risk row: "
            + product_id
            + " "
            + horizon
        )

    risk[
        product_id
    ][
        horizon
    ] = row


purchase_rows: list[
    dict[str, object]
] = []


rank_groups: set[int] = set()

q25_below_count = 0
q50_below_count = 0
q10_below_count = 0

method_counts: Counter[str] = Counter()

evidence_counts: Counter[str] = Counter()


for ranked in ranking_rows:

    product_id = clean(
        ranked.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank ranked product ID"
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
            "ranked product lacks complete risk horizons: "
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
        ranked.get(
            "current_tcg_market_price_usd"
        )
    )

    if current_price <= 0:
        fail(
            "non-positive current price: "
            + product_id
        )


    point_value = parse_float(
        ranked.get(
            "certified_1y_point_forecast_usd"
        )
    )

    q10 = parse_float(
        y1.get(
            "q10_terminal_value_usd"
        )
    )

    q25 = parse_float(
        y1.get(
            "q25_terminal_value_usd"
        )
    )

    q50 = parse_float(
        y1.get(
            "q50_terminal_value_usd"
        )
    )

    q75 = parse_float(
        y1.get(
            "q75_terminal_value_usd"
        )
    )

    q90 = parse_float(
        y1.get(
            "q90_terminal_value_usd"
        )
    )


    if not (
        q10
        <= q25
        <= q50
        <= q75
        <= q90
    ):
        fail(
            "non-monotonic Y1 purchase quantiles: "
            + product_id
        )


    probability_loss = parse_float(
        y1.get(
            "probability_of_loss"
        )
    )

    probability_positive = parse_float(
        y1.get(
            "probability_of_positive_return"
        )
    )

    downside_tail = parse_float(
        y1.get(
            "downside_tail_mean_total_return"
        )
    )

    upside_tail = parse_float(
        y1.get(
            "upside_tail_mean_total_return"
        )
    )


    if not (
        0.0 <= probability_loss <= 1.0
    ):
        fail(
            "invalid Y1 loss probability: "
            + product_id
        )

    if not (
        0.0 <= probability_positive <= 1.0
    ):
        fail(
            "invalid Y1 positive-return probability: "
            + product_id
        )


    competition_rank = parse_int(
        ranked.get(
            "competition_rank"
        )
    )

    rank_group = parse_int(
        ranked.get(
            "rank_group_index"
        )
    )

    rank_groups.add(
        rank_group
    )


    q10_margin = relative_margin(
        q10,
        current_price,
    )

    q25_margin = relative_margin(
        q25,
        current_price,
    )

    q50_margin = relative_margin(
        q50,
        current_price,
    )

    q75_margin = relative_margin(
        q75,
        current_price,
    )

    q90_margin = relative_margin(
        q90,
        current_price,
    )


    q10_state = factual_price_state(
        current_price,
        q10,
    )

    q25_state = factual_price_state(
        current_price,
        q25,
    )

    q50_state = factual_price_state(
        current_price,
        q50,
    )


    if q10_state == "CURRENT_PRICE_BELOW_BREAK_EVEN_LEVEL":
        q10_below_count += 1

    if q25_state == "CURRENT_PRICE_BELOW_BREAK_EVEN_LEVEL":
        q25_below_count += 1

    if q50_state == "CURRENT_PRICE_BELOW_BREAK_EVEN_LEVEL":
        q50_below_count += 1


    production_method = clean(
        ranked.get(
            "production_method"
        )
    )

    evidence_class = clean(
        ranked.get(
            "own_history_evidence_class"
        )
    )

    method_counts[
        production_method
    ] += 1

    evidence_counts[
        evidence_class
    ] += 1


    purchase_rows.append(
        {
            "competition_rank":
                competition_rank,

            "rank_group_index":
                rank_group,

            "rank_group_size":
                parse_int(
                    ranked.get(
                        "rank_group_size"
                    )
                ),

            "co_ranked_tie":
                parse_bool(
                    ranked.get(
                        "co_ranked_tie"
                    )
                ),

            "secret_lair_id":
                product_id,

            "product_name":
                clean(
                    ranked.get(
                        "product_name"
                    )
                ),

            "production_method":
                production_method,

            "modeling_method_class":
                clean(
                    ranked.get(
                        "modeling_method_class"
                    )
                ),

            "current_tcg_market_price_usd":
                current_price,

            "certified_1y_point_forecast_usd":
                point_value,

            "certified_1y_point_return":
                (
                    point_value
                    /
                    current_price
                ) - 1.0,

            # ---------------------------------------------------------------
            # Break-even entry prices
            #
            # Holding the governed future-value distribution fixed, each
            # terminal quantile is the purchase price at which that quantile
            # would represent exactly a 0% total return.
            # ---------------------------------------------------------------

            "y1_q10_break_even_entry_price_usd":
                q10,

            "y1_q25_break_even_entry_price_usd":
                q25,

            "y1_q50_break_even_entry_price_usd":
                q50,

            "y1_q75_break_even_entry_price_usd":
                q75,

            "y1_q90_break_even_entry_price_usd":
                q90,

            "current_price_margin_to_q10_break_even":
                q10_margin,

            "current_price_margin_to_q25_break_even":
                q25_margin,

            "current_price_margin_to_q50_break_even":
                q50_margin,

            "current_price_margin_to_q75_break_even":
                q75_margin,

            "current_price_margin_to_q90_break_even":
                q90_margin,

            "current_price_vs_q10_break_even_state":
                q10_state,

            "current_price_vs_q25_break_even_state":
                q25_state,

            "current_price_vs_q50_break_even_state":
                q50_state,

            "y1_probability_of_loss":
                probability_loss,

            "y1_probability_of_positive_return":
                probability_positive,

            "y1_downside_tail_mean_total_return":
                downside_tail,

            "y1_upside_tail_mean_total_return":
                upside_tail,

            "y1_q10_terminal_value_usd":
                q10,

            "y1_q25_terminal_value_usd":
                q25,

            "y1_q50_terminal_value_usd":
                q50,

            "y1_q75_terminal_value_usd":
                q75,

            "y1_q90_terminal_value_usd":
                q90,

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

            "y3_q10_terminal_value_scenario_usd":
                parse_float(
                    y3.get(
                        "q10_terminal_value_usd"
                    )
                ),

            "y3_q50_terminal_value_scenario_usd":
                parse_float(
                    y3.get(
                        "q50_terminal_value_usd"
                    )
                ),

            "y3_q90_terminal_value_scenario_usd":
                parse_float(
                    y3.get(
                        "q90_terminal_value_usd"
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

            "y5_q10_terminal_value_scenario_usd":
                parse_float(
                    y5.get(
                        "q10_terminal_value_usd"
                    )
                ),

            "y5_q50_terminal_value_scenario_usd":
                parse_float(
                    y5.get(
                        "q50_terminal_value_usd"
                    )
                ),

            "y5_q90_terminal_value_scenario_usd":
                parse_float(
                    y5.get(
                        "q90_terminal_value_usd"
                    )
                ),

            "own_history_evidence_class":
                evidence_class,

            "history_span_days":
                parse_int(
                    ranked.get(
                        "history_span_days"
                    )
                ),

            "historical_observation_count":
                parse_int(
                    ranked.get(
                        "historical_observation_count"
                    )
                ),

            "exact_structural_comparable_support":
                parse_bool(
                    ranked.get(
                        "exact_structural_comparable_support"
                    )
                ),

            "exact_structural_comparable_product_count":
                parse_int(
                    ranked.get(
                        "exact_structural_comparable_product_count"
                    )
                ),

            "global_comparable_product_count":
                parse_int(
                    ranked.get(
                        "global_comparable_product_count"
                    )
                ),

            "exact_structural_comparable_event_count":
                parse_int(
                    ranked.get(
                        "exact_structural_comparable_event_count"
                    )
                ),

            "global_comparable_event_count":
                parse_int(
                    ranked.get(
                        "global_comparable_event_count"
                    )
                ),

            "ranking_authority":
                "CERTIFIED",

            "purchase_analysis_status":
                "ECONOMIC_ANALYSIS_AVAILABLE",

            "purchase_recommendation":
                "NOT_ASSIGNED",

            "buy_wait_avoid_threshold_used":
                False,

            "collector_purchase_thresholds_reused":
                False,

            "transaction_cost_assumption_used":
                False,

            "automatic_purchase_execution":
                False,
        }
    )


if len(purchase_rows) != args.expected_products:
    fail(
        "purchase-analysis product population mismatch"
    )


if len(rank_groups) != args.expected_rank_groups:
    fail(
        "purchase-analysis rank-group count drift: "
        f"expected={args.expected_rank_groups}, "
        f"actual={len(rank_groups)}"
    )


ledger_path = (
    run_root
    /
    "secret_lair_v1_purchase_analysis.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_purchase_analysis_summary.json"
)


write_csv(
    ledger_path,
    purchase_rows,
    [
        "competition_rank",
        "rank_group_index",
        "rank_group_size",
        "co_ranked_tie",
        "secret_lair_id",
        "product_name",
        "production_method",
        "modeling_method_class",
        "current_tcg_market_price_usd",
        "certified_1y_point_forecast_usd",
        "certified_1y_point_return",
        "y1_q10_break_even_entry_price_usd",
        "y1_q25_break_even_entry_price_usd",
        "y1_q50_break_even_entry_price_usd",
        "y1_q75_break_even_entry_price_usd",
        "y1_q90_break_even_entry_price_usd",
        "current_price_margin_to_q10_break_even",
        "current_price_margin_to_q25_break_even",
        "current_price_margin_to_q50_break_even",
        "current_price_margin_to_q75_break_even",
        "current_price_margin_to_q90_break_even",
        "current_price_vs_q10_break_even_state",
        "current_price_vs_q25_break_even_state",
        "current_price_vs_q50_break_even_state",
        "y1_probability_of_loss",
        "y1_probability_of_positive_return",
        "y1_downside_tail_mean_total_return",
        "y1_upside_tail_mean_total_return",
        "y1_q10_terminal_value_usd",
        "y1_q25_terminal_value_usd",
        "y1_q50_terminal_value_usd",
        "y1_q75_terminal_value_usd",
        "y1_q90_terminal_value_usd",
        "y3_median_total_return_scenario",
        "y3_probability_of_loss_scenario",
        "y3_q10_terminal_value_scenario_usd",
        "y3_q50_terminal_value_scenario_usd",
        "y3_q90_terminal_value_scenario_usd",
        "y5_median_total_return_scenario",
        "y5_probability_of_loss_scenario",
        "y5_q10_terminal_value_scenario_usd",
        "y5_q50_terminal_value_scenario_usd",
        "y5_q90_terminal_value_scenario_usd",
        "own_history_evidence_class",
        "history_span_days",
        "historical_observation_count",
        "exact_structural_comparable_support",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "exact_structural_comparable_event_count",
        "global_comparable_event_count",
        "ranking_authority",
        "purchase_analysis_status",
        "purchase_recommendation",
        "buy_wait_avoid_threshold_used",
        "collector_purchase_thresholds_reused",
        "transaction_cost_assumption_used",
        "automatic_purchase_execution",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_PURCHASE_ECONOMICS_ANALYSIS_COMPLETE",

    "analyzed_products":
        len(
            purchase_rows
        ),

    "rank_groups":
        len(
            rank_groups
        ),

    "current_price_states": {
        "below_q10_break_even":
            q10_below_count,

        "below_q25_break_even":
            q25_below_count,

        "below_q50_break_even":
            q50_below_count,
    },

    "production_method_counts":
        dict(
            method_counts
        ),

    "evidence_class_counts":
        dict(
            evidence_counts
        ),

    "purchase_analysis": {
        "break_even_entry_prices_calculated":
            True,

        "quantile_break_even_levels": [
            "Q10",
            "Q25",
            "Q50",
            "Q75",
            "Q90",
        ],

        "probability_of_loss_included":
            True,

        "downside_tail_included":
            True,

        "upside_tail_included":
            True,

        "three_year_scenarios_included":
            True,

        "five_year_scenarios_included":
            True,

        "comparable_evidence_included":
            True,

        "history_evidence_included":
            True,
    },

    "governance": {
        "new_recommendation_thresholds":
            False,

        "collector_recommendation_thresholds_reused":
            False,

        "weighted_purchase_score":
            False,

        "transaction_cost_assumption":
            False,

        "buy_wait_avoid_label_assigned":
            False,

        "purchase_recommendation_assigned":
            False,

        "automatic_purchase_execution":
            False,
    },

    "authority": {
        "purchase_analysis":
            True,

        "recommendation_policy_execution":
            True,

        "purchase_recommendation":
            False,

        "UIP_delivery":
            False,

        "automatic_purchase_execution":
            False,
    },

    "next_gate":
        "SL6D_SECRET_LAIR_PURCHASE_RECOMMENDATION_POLICY_AND_CERTIFICATION",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_PURCHASE_ANALYSIS=PASS"
)

print(
    "ANALYZED_PRODUCTS="
    + str(
        len(
            purchase_rows
        )
    )
)

print(
    "RANK_GROUPS="
    + str(
        len(
            rank_groups
        )
    )
)

print(
    "CURRENT_PRICE_BELOW_Q10_BREAK_EVEN="
    + str(
        q10_below_count
    )
)

print(
    "CURRENT_PRICE_BELOW_Q25_BREAK_EVEN="
    + str(
        q25_below_count
    )
)

print(
    "CURRENT_PRICE_BELOW_Q50_BREAK_EVEN="
    + str(
        q50_below_count
    )
)

print(
    "BREAK_EVEN_ENTRY_PRICES_CALCULATED=TRUE"
)

print(
    "PROBABILITY_OF_LOSS_INCLUDED=TRUE"
)

print(
    "DOWNSIDE_TAIL_INCLUDED=TRUE"
)

print(
    "LONG_HORIZON_SCENARIOS_INCLUDED=TRUE"
)

print(
    "COMPARABLE_EVIDENCE_INCLUDED=TRUE"
)

print(
    "NEW_RECOMMENDATION_THRESHOLDS=FALSE"
)

print(
    "COLLECTOR_RECOMMENDATION_THRESHOLDS_REUSED=FALSE"
)

print(
    "BUY_WAIT_AVOID_LABEL_ASSIGNED=FALSE"
)

print(
    "PURCHASE_ANALYSIS_CERTIFIED=TRUE"
)

print(
    "RECOMMENDATION_POLICY_EXECUTION_AUTHORIZED=TRUE"
)

print(
    "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
)

print(
    "NEXT_GATE=SL6D_SECRET_LAIR_PURCHASE_RECOMMENDATION_POLICY_AND_CERTIFICATION"
)