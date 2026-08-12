from __future__ import annotations

import argparse
import csv
import json
import math

from collections import Counter
from pathlib import Path


NO_DIRECT_HISTORY = (
    "NO_DIRECT_HISTORY_CURRENT_PRICE_ONLY"
)


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


parser = argparse.ArgumentParser()

parser.add_argument(
    "--purchase-analysis",
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

parser.add_argument(
    "--expected-below-q10",
    required=True,
    type=int,
)

args = parser.parse_args()


rows = read_csv(
    Path(
        args.purchase_analysis
    )
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


if len(rows) != args.expected_products:
    fail(
        "recommendation population drift: "
        f"expected={args.expected_products}, "
        f"actual={len(rows)}"
    )


recommendation_rows: list[
    dict[str, object]
] = []

recommendation_counts: Counter[str] = Counter()

evidence_qualifier_counts: Counter[str] = Counter()

rank_groups: set[int] = set()

numeric_below_q10 = 0
numeric_equal_q10 = 0


for row in rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank Secret Lair ID"
        )


    current_price = parse_float(
        row.get(
            "current_tcg_market_price_usd"
        )
    )

    q10_entry = parse_float(
        row.get(
            "y1_q10_break_even_entry_price_usd"
        )
    )

    q25_entry = parse_float(
        row.get(
            "y1_q25_break_even_entry_price_usd"
        )
    )

    q50_entry = parse_float(
        row.get(
            "y1_q50_break_even_entry_price_usd"
        )
    )


    if not (
        current_price > 0
        and
        q10_entry > 0
        and
        q25_entry > 0
        and
        q50_entry > 0
    ):
        fail(
            "non-positive purchase economics for "
            + product_id
        )


    if not (
        q10_entry
        <= q25_entry
        <= q50_entry
    ):
        fail(
            "non-monotonic purchase quantiles for "
            + product_id
        )


    if current_price < q10_entry:
        numeric_below_q10 += 1

    elif current_price == q10_entry:
        numeric_equal_q10 += 1


    history_class = clean(
        row.get(
            "own_history_evidence_class"
        )
    )

    exact_support = parse_bool(
        row.get(
            "exact_structural_comparable_support"
        )
    )

    exact_peer_count = parse_int(
        row.get(
            "exact_structural_comparable_product_count"
        )
    )

    global_peer_count = parse_int(
        row.get(
            "global_comparable_product_count"
        )
    )

    exact_event_count = parse_int(
        row.get(
            "exact_structural_comparable_event_count"
        )
    )

    global_event_count = parse_int(
        row.get(
            "global_comparable_event_count"
        )
    )


    if history_class == "ESTABLISHED_DIRECT_HISTORY":

        evidence_qualifier = (
            "ESTABLISHED_DIRECT_HISTORY"
        )

        evidence_gate_for_q10_candidate = True

    elif history_class == "SHORT_DIRECT_HISTORY":

        if exact_support:

            evidence_qualifier = (
                "SHORT_HISTORY_PLUS_EXACT_COMPARABLES"
            )

        else:

            evidence_qualifier = (
                "SHORT_HISTORY_GLOBAL_COMPARABLES"
            )

        evidence_gate_for_q10_candidate = True

    elif history_class == NO_DIRECT_HISTORY:

        if (
            exact_support
            and
            exact_peer_count > 0
            and
            exact_event_count > 0
        ):

            evidence_qualifier = (
                "NO_HISTORY_EXACT_STRUCTURAL_COMPARABLES"
            )

            evidence_gate_for_q10_candidate = True

        else:

            if (
                global_peer_count <= 0
                or
                global_event_count <= 0
            ):
                fail(
                    "no-history product lacks governed comparable evidence: "
                    + product_id
                )

            evidence_qualifier = (
                "NO_HISTORY_GLOBAL_COMPARABLES_ONLY"
            )

            evidence_gate_for_q10_candidate = False

    else:

        fail(
            "unexpected evidence class: "
            + history_class
        )


    # -----------------------------------------------------------------------
    # Recommendation policy.
    #
    # Q10 is the previously governed downside quantile.
    #
    # No rank cutoff, score, or Collector recommendation rule enters here.
    # -----------------------------------------------------------------------

    at_or_below_q10 = (
        current_price <= q10_entry
    )


    if at_or_below_q10:

        if evidence_gate_for_q10_candidate:

            recommendation = (
                "BUY_CANDIDATE_NOW"
            )

            recommendation_reason = (
                "CURRENT_PRICE_AT_OR_BELOW_GOVERNED_Q10_ENTRY_AND_EVIDENCE_GATE_PASSED"
            )

        else:

            recommendation = (
                "REVIEW_GLOBAL_COMPARABLE_ONLY"
            )

            recommendation_reason = (
                "CURRENT_PRICE_AT_OR_BELOW_GOVERNED_Q10_ENTRY_BUT_NO_DIRECT_HISTORY_OR_EXACT_STRUCTURAL_COMPARABLE"
            )

    else:

        recommendation = (
            "WAIT_FOR_Q10_ENTRY"
        )

        recommendation_reason = (
            "CURRENT_PRICE_ABOVE_GOVERNED_Q10_ENTRY"
        )


    required_price_change_to_q10 = (
        q10_entry
        /
        current_price
    ) - 1.0


    recommendation_counts[
        recommendation
    ] += 1

    evidence_qualifier_counts[
        evidence_qualifier
    ] += 1

    rank_group = parse_int(
        row.get(
            "rank_group_index"
        )
    )

    rank_groups.add(
        rank_group
    )


    recommendation_rows.append(
        {
            "competition_rank":
                parse_int(
                    row.get(
                        "competition_rank"
                    )
                ),

            "rank_group_index":
                rank_group,

            "rank_group_size":
                parse_int(
                    row.get(
                        "rank_group_size"
                    )
                ),

            "co_ranked_tie":
                parse_bool(
                    row.get(
                        "co_ranked_tie"
                    )
                ),

            "secret_lair_id":
                product_id,

            "product_name":
                clean(
                    row.get(
                        "product_name"
                    )
                ),

            "purchase_recommendation":
                recommendation,

            "recommendation_reason":
                recommendation_reason,

            "evidence_qualifier":
                evidence_qualifier,

            "evidence_gate_for_q10_candidate":
                evidence_gate_for_q10_candidate,

            "current_tcg_market_price_usd":
                current_price,

            "q10_entry_price_usd":
                q10_entry,

            "required_price_change_to_q10_entry":
                required_price_change_to_q10,

            "q25_break_even_price_usd":
                q25_entry,

            "q50_break_even_price_usd":
                q50_entry,

            "certified_1y_point_forecast_usd":
                parse_float(
                    row.get(
                        "certified_1y_point_forecast_usd"
                    )
                ),

            "certified_1y_point_return":
                parse_float(
                    row.get(
                        "certified_1y_point_return"
                    )
                ),

            "y1_probability_of_loss":
                parse_float(
                    row.get(
                        "y1_probability_of_loss"
                    )
                ),

            "y1_probability_of_positive_return":
                parse_float(
                    row.get(
                        "y1_probability_of_positive_return"
                    )
                ),

            "y1_downside_tail_mean_total_return":
                parse_float(
                    row.get(
                        "y1_downside_tail_mean_total_return"
                    )
                ),

            "y1_upside_tail_mean_total_return":
                parse_float(
                    row.get(
                        "y1_upside_tail_mean_total_return"
                    )
                ),

            "y3_median_total_return_scenario":
                parse_float(
                    row.get(
                        "y3_median_total_return_scenario"
                    )
                ),

            "y3_probability_of_loss_scenario":
                parse_float(
                    row.get(
                        "y3_probability_of_loss_scenario"
                    )
                ),

            "y5_median_total_return_scenario":
                parse_float(
                    row.get(
                        "y5_median_total_return_scenario"
                    )
                ),

            "y5_probability_of_loss_scenario":
                parse_float(
                    row.get(
                        "y5_probability_of_loss_scenario"
                    )
                ),

            "own_history_evidence_class":
                history_class,

            "exact_structural_comparable_support":
                exact_support,

            "exact_structural_comparable_product_count":
                exact_peer_count,

            "global_comparable_product_count":
                global_peer_count,

            "exact_structural_comparable_event_count":
                exact_event_count,

            "global_comparable_event_count":
                global_event_count,

            "recommendation_policy":
                "SECRET_LAIR_V1_Q10_CONSERVATIVE_ENTRY_POLICY",

            "recommendation_uses_rank_cutoff":
                False,

            "recommendation_uses_weighted_score":
                False,

            "collector_thresholds_reused":
                False,

            "q25_or_q50_used_as_buy_threshold":
                False,

            "transaction_costs_included":
                False,

            "three_or_five_year_scenario_used_as_buy_trigger":
                False,

            "automatic_purchase_execution":
                False,
        }
    )


if len(recommendation_rows) != args.expected_products:
    fail(
        "recommendation row count mismatch"
    )


if len(rank_groups) != args.expected_rank_groups:
    fail(
        "recommendation rank-group count drift"
    )


if numeric_below_q10 != args.expected_below_q10:
    fail(
        "Q10 snapshot state drift: "
        f"expected below={args.expected_below_q10}, "
        f"actual below={numeric_below_q10}"
    )


if sum(
    recommendation_counts.values()
) != args.expected_products:
    fail(
        "recommendation category population mismatch"
    )


ledger_path = (
    run_root
    /
    "secret_lair_v1_purchase_recommendations.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_purchase_recommendation_summary.json"
)


write_csv(
    ledger_path,
    recommendation_rows,
    [
        "competition_rank",
        "rank_group_index",
        "rank_group_size",
        "co_ranked_tie",
        "secret_lair_id",
        "product_name",
        "purchase_recommendation",
        "recommendation_reason",
        "evidence_qualifier",
        "evidence_gate_for_q10_candidate",
        "current_tcg_market_price_usd",
        "q10_entry_price_usd",
        "required_price_change_to_q10_entry",
        "q25_break_even_price_usd",
        "q50_break_even_price_usd",
        "certified_1y_point_forecast_usd",
        "certified_1y_point_return",
        "y1_probability_of_loss",
        "y1_probability_of_positive_return",
        "y1_downside_tail_mean_total_return",
        "y1_upside_tail_mean_total_return",
        "y3_median_total_return_scenario",
        "y3_probability_of_loss_scenario",
        "y5_median_total_return_scenario",
        "y5_probability_of_loss_scenario",
        "own_history_evidence_class",
        "exact_structural_comparable_support",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "exact_structural_comparable_event_count",
        "global_comparable_event_count",
        "recommendation_policy",
        "recommendation_uses_rank_cutoff",
        "recommendation_uses_weighted_score",
        "collector_thresholds_reused",
        "q25_or_q50_used_as_buy_threshold",
        "transaction_costs_included",
        "three_or_five_year_scenario_used_as_buy_trigger",
        "automatic_purchase_execution",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_PURCHASE_RECOMMENDATION_COMPLETE",

    "products":
        len(
            recommendation_rows
        ),

    "rank_groups":
        len(
            rank_groups
        ),

    "recommendation_counts":
        dict(
            recommendation_counts
        ),

    "evidence_qualifier_counts":
        dict(
            evidence_qualifier_counts
        ),

    "q10_snapshot": {
        "current_price_below_q10":
            numeric_below_q10,

        "current_price_equal_q10":
            numeric_equal_q10,
    },

    "policy": {
        "policy_id":
            "SECRET_LAIR_V1_Q10_CONSERVATIVE_ENTRY_POLICY",

        "buy_candidate_rule":
            "CURRENT_PRICE_AT_OR_BELOW_GOVERNED_1Y_Q10_ENTRY_AND_EVIDENCE_GATE_PASSED",

        "global_only_no_history_rule":
            "REVIEW_GLOBAL_COMPARABLE_ONLY",

        "wait_rule":
            "CURRENT_PRICE_ABOVE_GOVERNED_1Y_Q10_ENTRY",

        "q10_selected_before_this_policy_as_governed_uncertainty_output":
            True,

        "policy_optimized_to_current_candidate_count":
            False,

        "rank_cutoff":
            False,

        "weighted_purchase_score":
            False,

        "collector_thresholds_reused":
            False,

        "q25_buy_threshold":
            False,

        "q50_buy_threshold":
            False,

        "transaction_cost_assumption":
            False,

        "long_horizon_scenario_buy_trigger":
            False,
    },

    "authority": {
        "purchase_recommendation":
            True,

        "Secret_Lair_V1_closeout_execution":
            True,

        "Secret_Lair_V1_closed":
            False,

        "UIP_delivery":
            False,

        "automatic_purchase_execution":
            False,
    },

    "next_gate":
        "SL7_SECRET_LAIR_V1_FINAL_CLOSEOUT",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_PURCHASE_RECOMMENDATION=PASS"
)

print(
    "PRODUCTS="
    + str(
        len(
            recommendation_rows
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

for category in (
    "BUY_CANDIDATE_NOW",
    "REVIEW_GLOBAL_COMPARABLE_ONLY",
    "WAIT_FOR_Q10_ENTRY",
):

    print(
        category
        + "="
        + str(
            recommendation_counts.get(
                category,
                0,
            )
        )
    )


print(
    "CURRENT_PRICE_BELOW_Q10="
    + str(
        numeric_below_q10
    )
)

print(
    "CURRENT_PRICE_EQUAL_Q10="
    + str(
        numeric_equal_q10
    )
)

print(
    "Q10_CONSERVATIVE_ENTRY_POLICY=TRUE"
)

print(
    "POLICY_OPTIMIZED_TO_CURRENT_CANDIDATE_COUNT=FALSE"
)

print(
    "NO_HISTORY_GLOBAL_ONLY_REQUIRES_REVIEW=TRUE"
)

print(
    "RANK_CUTOFF_USED=FALSE"
)

print(
    "WEIGHTED_PURCHASE_SCORE=FALSE"
)

print(
    "COLLECTOR_THRESHOLDS_REUSED=FALSE"
)

print(
    "Q25_OR_Q50_BUY_THRESHOLD=FALSE"
)

print(
    "LONG_HORIZON_SCENARIO_BUY_TRIGGER=FALSE"
)

print(
    "PURCHASE_RECOMMENDATION_CERTIFIED=TRUE"
)

print(
    "AUTOMATIC_PURCHASE_EXECUTION=FALSE"
)

print(
    "NEXT_GATE=SL7_SECRET_LAIR_V1_FINAL_CLOSEOUT"
)