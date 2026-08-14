from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


BUY = "BUY_CANDIDATE_NOW"
WAIT = "WAIT_FOR_Q10_ENTRY"
REVIEW = "REVIEW_GLOBAL_COMPARABLE_ONLY"

NO_HISTORY = "NO_DIRECT_HISTORY_CURRENT_PRICE_ONLY"


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def to_bool(value: object) -> bool:
    text = clean(value).lower()

    if text == "true":
        return True

    if text == "false":
        return False

    fail(
        "invalid boolean value: "
        + clean(value)
    )


def to_float(value: object) -> float:
    result = float(
        clean(value)
    )

    if not math.isfinite(result):
        fail(
            "non-finite numeric value"
        )

    return result


def read_csv(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        reader = csv.DictReader(
            handle
        )

        return (
            list(
                reader.fieldnames
                or []
            ),
            list(
                reader
            ),
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
        writer.writerows(
            rows
        )


parser = argparse.ArgumentParser()

parser.add_argument(
    "--purchase",
    required=True,
)

parser.add_argument(
    "--ranking",
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
    "--expected-buy",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-review",
    required=True,
    type=int,
)

parser.add_argument(
    "--expected-wait",
    required=True,
    type=int,
)

args = parser.parse_args()


purchase_fields, purchase_rows = read_csv(
    Path(
        args.purchase
    )
)

_, ranking_rows = read_csv(
    Path(
        args.ranking
    )
)


if len(purchase_rows) != args.expected_products:
    fail(
        "purchase population drift"
    )

if len(ranking_rows) != args.expected_products:
    fail(
        "ranking population drift"
    )


ranking_by_id: dict[
    str,
    dict[str, str]
] = {}


for row in ranking_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank ranking product ID"
        )

    if product_id in ranking_by_id:
        fail(
            "duplicate ranking product ID: "
            + product_id
        )

    ranking_by_id[
        product_id
    ] = row


overlay_rows: list[
    dict[str, object]
] = []


recommendation_counts = {
    BUY: 0,
    REVIEW: 0,
    WAIT: 0,
}


direct_history_buys = 0
no_history_buys = 0
no_history_exact_support_buys = 0
no_history_global_only_buys = 0
buy_evidence_gate_failures = 0

review_global_only_rows = 0

minimum_buy_dollar_cushion: float | None = None
maximum_buy_dollar_cushion: float | None = None

minimum_buy_percent_cushion: float | None = None
maximum_buy_percent_cushion: float | None = None


for source in purchase_rows:

    product_id = clean(
        source.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank purchase product ID"
        )

    rank = ranking_by_id.get(
        product_id
    )

    if rank is None:
        fail(
            "purchase product missing ranking row: "
            + product_id
        )

    recommendation = clean(
        source.get(
            "purchase_recommendation"
        )
    )

    if recommendation not in recommendation_counts:
        fail(
            "unexpected recommendation: "
            + recommendation
        )

    recommendation_counts[
        recommendation
    ] += 1


    current_price = to_float(
        source.get(
            "current_tcg_market_price_usd"
        )
    )

    q10 = to_float(
        source.get(
            "q10_entry_price_usd"
        )
    )

    if current_price <= 0:
        fail(
            "non-positive current price: "
            + product_id
        )

    dollar_cushion = (
        q10
        -
        current_price
    )

    percent_cushion = (
        dollar_cushion
        /
        current_price
    )


    evidence_class = clean(
        source.get(
            "own_history_evidence_class"
        )
    )

    evidence_qualifier = clean(
        source.get(
            "evidence_qualifier"
        )
    )

    exact_support = to_bool(
        source.get(
            "exact_structural_comparable_support"
        )
    )

    evidence_gate = to_bool(
        source.get(
            "evidence_gate_for_q10_candidate"
        )
    )

    transaction_costs_included = to_bool(
        source.get(
            "transaction_costs_included"
        )
    )


    if transaction_costs_included:
        fail(
            "transaction costs unexpectedly modeled"
        )


    no_direct_history = (
        evidence_class
        ==
        NO_HISTORY
    )

    global_only = (
        no_direct_history
        and
        not exact_support
    )


    price_condition_met = (
        current_price
        <=
        q10
    )

    model_qualified = (
        recommendation
        ==
        BUY
    )


    if recommendation == BUY:

        if not price_condition_met:
            fail(
                "BUY above Q10: "
                + product_id
            )

        if not evidence_gate:
            buy_evidence_gate_failures += 1

        if no_direct_history:

            no_history_buys += 1

            if exact_support:
                no_history_exact_support_buys += 1
            else:
                no_history_global_only_buys += 1

        else:
            direct_history_buys += 1


        if minimum_buy_dollar_cushion is None:
            minimum_buy_dollar_cushion = dollar_cushion
            maximum_buy_dollar_cushion = dollar_cushion
            minimum_buy_percent_cushion = percent_cushion
            maximum_buy_percent_cushion = percent_cushion

        else:

            minimum_buy_dollar_cushion = min(
                minimum_buy_dollar_cushion,
                dollar_cushion,
            )

            maximum_buy_dollar_cushion = max(
                maximum_buy_dollar_cushion,
                dollar_cushion,
            )

            minimum_buy_percent_cushion = min(
                minimum_buy_percent_cushion,
                percent_cushion,
            )

            maximum_buy_percent_cushion = max(
                maximum_buy_percent_cushion,
                percent_cushion,
            )


    elif recommendation == WAIT:

        if price_condition_met:
            fail(
                "WAIT at or below Q10: "
                + product_id
            )


    elif recommendation == REVIEW:

        if global_only:
            review_global_only_rows += 1


    if recommendation == BUY:

        semantic_class = (
            "MODEL_QUALIFIED_ENTRY_CANDIDATE"
        )

        manual_execution_check = True

    elif recommendation == WAIT:

        semantic_class = (
            "MODEL_ENTRY_PRICE_CONDITION_NOT_SATISFIED"
        )

        manual_execution_check = False

    else:

        semantic_class = (
            "MODEL_EVIDENCE_REVIEW_REQUIRED"
        )

        manual_execution_check = False


    overlay_rows.append(
        {
            "secret_lair_id":
                product_id,

            "product_name":
                clean(
                    source.get(
                        "product_name"
                    )
                ),

            "v1_1_production_competition_rank":
                clean(
                    rank.get(
                        "v1_1_production_competition_rank"
                    )
                ),

            "purchase_recommendation":
                recommendation,

            "purchase_recommendation_semantic_class":
                semantic_class,

            "model_entry_price_condition_met":
                price_condition_met,

            "model_evidence_gate_passed":
                evidence_gate,

            "model_qualified_entry_candidate":
                model_qualified,

            "model_entry_ceiling_usd":
                q10,

            "current_tcg_market_price_usd":
                current_price,

            "q10_model_cushion_usd":
                dollar_cushion,

            "q10_model_cushion_fraction":
                percent_cushion,

            "own_history_evidence_class":
                evidence_class,

            "evidence_qualifier":
                evidence_qualifier,

            "no_direct_history":
                no_direct_history,

            "exact_structural_comparable_support":
                exact_support,

            "global_comparable_only":
                global_only,

            "transaction_costs_modeled":
                False,

            "execution_price_authority":
                "NOT_CERTIFIED",

            "execution_ready_purchase_certified":
                False,

            "manual_execution_price_check_required":
                manual_execution_check,

            "automatic_purchase_execution":
                False,
        }
    )


if recommendation_counts[BUY] != args.expected_buy:
    fail(
        "BUY count drift"
    )

if recommendation_counts[REVIEW] != args.expected_review:
    fail(
        "REVIEW count drift"
    )

if recommendation_counts[WAIT] != args.expected_wait:
    fail(
        "WAIT count drift"
    )

if buy_evidence_gate_failures != 0:
    fail(
        "BUY evidence-gate failures detected"
    )

if no_history_global_only_buys != 0:
    fail(
        "global-only BUY detected"
    )

if no_history_exact_support_buys != no_history_buys:
    fail(
        "not all no-history BUYs have exact support"
    )

if review_global_only_rows != args.expected_review:
    fail(
        "REVIEW population is not fully reconciled as global-only"
    )


run_root = Path(
    args.run_root
)

overlay_path = (
    run_root
    /
    "secret_lair_v1_1_purchase_actionability.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_1_purchase_actionability_summary.json"
)


write_csv(
    overlay_path,
    overlay_rows,
    list(
        overlay_rows[0].keys()
    ),
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_PURCHASE_ACTIONABILITY_SEMANTICS_RECONCILED",

    "population": {
        "products":
            len(
                overlay_rows
            ),

        "BUY_CANDIDATE_NOW":
            recommendation_counts[BUY],

        "REVIEW_GLOBAL_COMPARABLE_ONLY":
            recommendation_counts[REVIEW],

        "WAIT_FOR_Q10_ENTRY":
            recommendation_counts[WAIT],
    },

    "buy_evidence": {
        "direct_history_buys":
            direct_history_buys,

        "no_direct_history_buys":
            no_history_buys,

        "no_history_with_exact_structural_support":
            no_history_exact_support_buys,

        "no_history_global_only_buys":
            no_history_global_only_buys,

        "buy_evidence_gate_failures":
            buy_evidence_gate_failures,
    },

    "review_evidence": {
        "global_comparable_only_review_rows":
            review_global_only_rows,
    },

    "buy_cushion_snapshot": {
        "minimum_dollar_cushion_usd":
            minimum_buy_dollar_cushion,

        "maximum_dollar_cushion_usd":
            maximum_buy_dollar_cushion,

        "minimum_fractional_cushion":
            minimum_buy_percent_cushion,

        "maximum_fractional_cushion":
            maximum_buy_percent_cushion,

        "snapshot_diagnostic_only":
            True,

        "new_threshold_created":
            False,
    },

    "semantics": {
        "BUY_CANDIDATE_NOW":
            "MODEL_QUALIFIED_ENTRY_CANDIDATE",

        "BUY_label_changed":
            False,

        "q10_role":
            "EXISTING_MODEL_ENTRY_CEILING",

        "execution_price_authority":
            "NOT_CERTIFIED",

        "execution_ready_purchase_certified":
            False,

        "manual_execution_price_check_required_for_BUY":
            True,

        "transaction_costs_modeled":
            False,

        "automatic_purchase_execution":
            False,
    },

    "governance": {
        "forecast_changed":
            False,

        "Monte_Carlo_changed":
            False,

        "ranking_changed":
            False,

        "purchase_recommendation_changed":
            False,

        "purchase_policy_changed":
            False,

        "new_purchase_threshold_created":
            False,

        "marketplace_calls":
            0,

        "ebay_calls":
            0,
    },

    "next_gate":
        "SL8G_SECRET_LAIR_V1_1_FINAL_CLOSEOUT",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_V1_1_SL8F2=PASS"
)

print(
    "PRODUCTS="
    + str(
        len(
            overlay_rows
        )
    )
)

print(
    "BUY_CANDIDATE_NOW="
    + str(
        recommendation_counts[BUY]
    )
)

print(
    "DIRECT_HISTORY_BUYS="
    + str(
        direct_history_buys
    )
)

print(
    "NO_DIRECT_HISTORY_BUYS="
    + str(
        no_history_buys
    )
)

print(
    "NO_HISTORY_WITH_EXACT_STRUCTURAL_SUPPORT="
    + str(
        no_history_exact_support_buys
    )
)

print(
    "NO_HISTORY_GLOBAL_ONLY_BUYS="
    + str(
        no_history_global_only_buys
    )
)

print(
    "GLOBAL_ONLY_REVIEW_ROWS="
    + str(
        review_global_only_rows
    )
)

print(
    "BUY_RECOMMENDATION_SEMANTIC=MODEL_QUALIFIED_ENTRY_CANDIDATE"
)

print(
    "EXECUTION_PRICE_AUTHORITY=NOT_CERTIFIED"
)

print(
    "EXECUTION_READY_PURCHASE_CERTIFIED=FALSE"
)

print(
    "MANUAL_EXECUTION_PRICE_CHECK_REQUIRED_FOR_BUY=TRUE"
)

print(
    "PURCHASE_RECOMMENDATIONS_CHANGED=0"
)

print(
    "NEW_PURCHASE_THRESHOLD_CREATED=FALSE"
)

print(
    "NEXT_GATE=SL8G_SECRET_LAIR_V1_1_FINAL_CLOSEOUT"
)