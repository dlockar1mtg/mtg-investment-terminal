from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


PRODUCTION_FIELDS = (
    "v1_1_production_competition_rank",
    "v1_1_production_rank_group_index",
    "v1_1_production_rank_group_size",
    "v1_1_production_co_ranked_tie",
    "v1_1_production_ranking_method",
)


PURCHASE_RANK_FIELDS = (
    "v1_1_production_competition_rank",
    "v1_1_production_rank_group_index",
    "v1_1_production_rank_group_size",
    "v1_1_production_co_ranked_tie",
    "v1_1_production_ranking_method",
    "v1_1_ranking_changes_purchase_recommendation",
)


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def read_csv(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        reader = csv.DictReader(handle)

        return (
            list(reader.fieldnames or []),
            list(reader),
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


def index_unique(
    rows: list[dict[str, str]],
    label: str,
) -> dict[str, dict[str, str]]:

    indexed: dict[str, dict[str, str]] = {}

    for row in rows:

        product_id = clean(
            row.get(
                "secret_lair_id"
            )
        )

        if not product_id:
            fail(
                "blank product identity in "
                + label
            )

        if product_id in indexed:
            fail(
                "duplicate product identity in "
                + label
                + ": "
                + product_id
            )

        indexed[product_id] = row

    return indexed


parser = argparse.ArgumentParser()

parser.add_argument(
    "--candidate",
    required=True,
)

parser.add_argument(
    "--purchase",
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


candidate_fields, candidate_rows = read_csv(
    Path(
        args.candidate
    )
)

purchase_fields, purchase_rows = read_csv(
    Path(
        args.purchase
    )
)


if not candidate_rows:
    fail(
        "validated ranking candidate is empty"
    )

if not purchase_rows:
    fail(
        "V1 purchase recommendation authority is empty"
    )


candidate_by_product = index_unique(
    candidate_rows,
    "ranking candidate",
)

purchase_by_product = index_unique(
    purchase_rows,
    "purchase recommendations",
)


if len(candidate_rows) != args.expected_products:
    fail(
        "candidate product-count drift"
    )


if len(purchase_rows) != args.expected_products:
    fail(
        "purchase recommendation product-count drift"
    )


if set(candidate_by_product) != set(purchase_by_product):

    missing_from_purchase = sorted(
        set(candidate_by_product)
        -
        set(purchase_by_product)
    )

    missing_from_ranking = sorted(
        set(purchase_by_product)
        -
        set(candidate_by_product)
    )

    fail(
        "ranking/purchase universe mismatch; "
        f"missing_from_purchase={len(missing_from_purchase)}; "
        f"missing_from_ranking={len(missing_from_ranking)}"
    )


# ---------------------------------------------------------------------------
# 1. Promote the already-validated candidate.
#
# The complete validated candidate row is preserved.
#
# Explicit production aliases are appended so downstream consumers do not
# need to reinterpret "candidate" fields.
# ---------------------------------------------------------------------------

production_rows: list[
    dict[str, object]
] = []


for source in candidate_rows:

    output: dict[str, object] = dict(
        source
    )

    output[
        "v1_1_production_competition_rank"
    ] = int(
        clean(
            source[
                "v1_1_candidate_competition_rank"
            ]
        )
    )

    output[
        "v1_1_production_rank_group_index"
    ] = int(
        clean(
            source[
                "v1_1_candidate_rank_group_index"
            ]
        )
    )

    output[
        "v1_1_production_rank_group_size"
    ] = int(
        clean(
            source[
                "v1_1_candidate_rank_group_size"
            ]
        )
    )

    output[
        "v1_1_production_co_ranked_tie"
    ] = clean(
        source[
            "v1_1_candidate_co_ranked_tie"
        ]
    )

    output[
        "v1_1_production_ranking_method"
    ] = clean(
        source[
            "ranking_signal_method"
        ]
    )

    production_rows.append(
        output
    )


production_group_ids = sorted(
    {
        int(
            row[
                "v1_1_production_rank_group_index"
            ]
        )
        for row
        in production_rows
    }
)


if len(production_group_ids) != args.expected_rank_groups:
    fail(
        "production rank-group count drift"
    )


if production_group_ids != list(
    range(
        1,
        args.expected_rank_groups + 1,
    )
):
    fail(
        "production rank-group indices not contiguous"
    )


# ---------------------------------------------------------------------------
# 2. Purchase reconciliation.
#
# Preserve EVERY V1 purchase recommendation field exactly.
#
# Append only explicit V1.1 production ranking metadata.
# ---------------------------------------------------------------------------

production_by_product = {
    clean(
        row[
            "secret_lair_id"
        ]
    ):
        row
    for row
    in production_rows
}


reconciled_purchase_rows: list[
    dict[str, object]
] = []


for original in purchase_rows:

    product_id = clean(
        original[
            "secret_lair_id"
        ]
    )

    rank = production_by_product[
        product_id
    ]

    output: dict[str, object] = dict(
        original
    )

    output[
        "v1_1_production_competition_rank"
    ] = rank[
        "v1_1_production_competition_rank"
    ]

    output[
        "v1_1_production_rank_group_index"
    ] = rank[
        "v1_1_production_rank_group_index"
    ]

    output[
        "v1_1_production_rank_group_size"
    ] = rank[
        "v1_1_production_rank_group_size"
    ]

    output[
        "v1_1_production_co_ranked_tie"
    ] = rank[
        "v1_1_production_co_ranked_tie"
    ]

    output[
        "v1_1_production_ranking_method"
    ] = rank[
        "v1_1_production_ranking_method"
    ]

    output[
        "v1_1_ranking_changes_purchase_recommendation"
    ] = False

    reconciled_purchase_rows.append(
        output
    )


# ---------------------------------------------------------------------------
# 3. Prove every original V1 purchase field is unchanged by product.
# ---------------------------------------------------------------------------

reconciled_by_product = {
    clean(
        row[
            "secret_lair_id"
        ]
    ):
        row
    for row
    in reconciled_purchase_rows
}


purchase_field_mutations = 0


for product_id in sorted(
    purchase_by_product
):

    original = purchase_by_product[
        product_id
    ]

    reconciled = reconciled_by_product[
        product_id
    ]

    for field in purchase_fields:

        if clean(
            original.get(
                field
            )
        ) != clean(
            reconciled.get(
                field
            )
        ):

            purchase_field_mutations += 1


if purchase_field_mutations != 0:
    fail(
        "V1 purchase field mutation count="
        + str(
            purchase_field_mutations
        )
    )


# ---------------------------------------------------------------------------
# 4. Prove purchase-policy controls remain unchanged and non-ranking-based.
# ---------------------------------------------------------------------------

for row in reconciled_purchase_rows:

    if clean(
        row.get(
            "recommendation_policy"
        )
    ) != "SECRET_LAIR_V1_Q10_CONSERVATIVE_ENTRY_POLICY":

        fail(
            "purchase-policy drift"
        )

    if clean(
        row.get(
            "recommendation_uses_rank_cutoff"
        )
    ).lower() != "false":

        fail(
            "rank cutoff unexpectedly used"
        )

    if clean(
        row.get(
            "recommendation_uses_weighted_score"
        )
    ).lower() != "false":

        fail(
            "weighted purchase score unexpectedly used"
        )

    if clean(
        row.get(
            "collector_thresholds_reused"
        )
    ).lower() != "false":

        fail(
            "Collector thresholds unexpectedly reused"
        )

    if clean(
        row.get(
            "q25_or_q50_used_as_buy_threshold"
        )
    ).lower() != "false":

        fail(
            "Q25/Q50 unexpectedly used as buy threshold"
        )

    if clean(
        row.get(
            "three_or_five_year_scenario_used_as_buy_trigger"
        )
    ).lower() != "false":

        fail(
            "3Y/5Y scenario unexpectedly used as buy trigger"
        )

    if clean(
        row.get(
            "automatic_purchase_execution"
        )
    ).lower() != "false":

        fail(
            "automatic purchase execution unexpectedly enabled"
        )


recommendation_counts = Counter(
    clean(
        row[
            "purchase_recommendation"
        ]
    )
    for row
    in reconciled_purchase_rows
)


buy_count = recommendation_counts.get(
    "BUY_CANDIDATE_NOW",
    0,
)

review_count = recommendation_counts.get(
    "REVIEW_GLOBAL_COMPARABLE_ONLY",
    0,
)

wait_count = recommendation_counts.get(
    "WAIT_FOR_Q10_ENTRY",
    0,
)


expected_labels = {
    "BUY_CANDIDATE_NOW",
    "REVIEW_GLOBAL_COMPARABLE_ONLY",
    "WAIT_FOR_Q10_ENTRY",
}


unexpected_labels = sorted(
    set(
        recommendation_counts
    )
    -
    expected_labels
)


if unexpected_labels:
    fail(
        "unexpected purchase recommendation labels: "
        +
        ",".join(
            unexpected_labels
        )
    )


if buy_count != args.expected_buy:
    fail(
        "BUY_CANDIDATE_NOW count drift"
    )

if review_count != args.expected_review:
    fail(
        "REVIEW_GLOBAL_COMPARABLE_ONLY count drift"
    )

if wait_count != args.expected_wait:
    fail(
        "WAIT_FOR_Q10_ENTRY count drift"
    )


if (
    buy_count
    +
    review_count
    +
    wait_count
) != args.expected_products:

    fail(
        "purchase recommendation total-count drift"
    )


# ---------------------------------------------------------------------------
# 5. Evidence outputs.
# ---------------------------------------------------------------------------

run_root = Path(
    args.run_root
)


production_path = (
    run_root
    /
    "secret_lair_v1_1_production_ranking.csv"
)


purchase_path = (
    run_root
    /
    "secret_lair_v1_1_purchase_recommendation_reconciliation.csv"
)


summary_path = (
    run_root
    /
    "secret_lair_v1_1_sl8f_summary.json"
)


write_csv(
    production_path,
    production_rows,
    list(
        candidate_fields
    )
    +
    list(
        PRODUCTION_FIELDS
    ),
)


write_csv(
    purchase_path,
    reconciled_purchase_rows,
    list(
        purchase_fields
    )
    +
    list(
        PURCHASE_RANK_FIELDS
    ),
)


summary = {
    "status":
        "SECRET_LAIR_V1_1_PRODUCTION_RANKING_PROMOTION_AND_PURCHASE_RECONCILIATION_COMPLETE",

    "production_ranking": {
        "products":
            len(
                production_rows
            ),

        "rank_groups":
            len(
                production_group_ids
            ),

        "source":
            "VALIDATED_SL8D_RANKING_SIGNAL_INTEGRATION_CANDIDATE",

        "V1_rank_group_hierarchy_preserved":
            True,

        "point_forecast_changed":
            False,

        "Monte_Carlo_changed":
            False,

        "weighted_ranking_score":
            False,
    },

    "purchase_reconciliation": {
        "rows":
            len(
                reconciled_purchase_rows
            ),

        "V1_purchase_fields_mutated":
            purchase_field_mutations,

        "purchase_policy":
            "SECRET_LAIR_V1_Q10_CONSERVATIVE_ENTRY_POLICY",

        "ranking_used_as_purchase_cutoff":
            False,

        "weighted_purchase_score":
            False,

        "purchase_policy_redesigned":
            False,

        "recommendations_changed_due_to_V1_1_ranking":
            0,

        "BUY_CANDIDATE_NOW":
            buy_count,

        "REVIEW_GLOBAL_COMPARABLE_ONLY":
            review_count,

        "WAIT_FOR_Q10_ENTRY":
            wait_count,
    },

    "governance": {
        "V1_files_mutated":
            False,

        "production_ranking_promoted":
            True,

        "purchase_recommendations_reconciled":
            True,

        "point_forecast_rebuilt":
            False,

        "Monte_Carlo_rebuilt":
            False,

        "Q10_recalculated":
            False,

        "new_buy_threshold_created":
            False,

        "eBay_used":
            False,

        "automatic_purchase_execution":
            False,
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
    "SECRET_LAIR_V1_1_SL8F=PASS"
)

print(
    "PRODUCTION_RANKED_PRODUCTS="
    +
    str(
        len(
            production_rows
        )
    )
)

print(
    "PRODUCTION_RANK_GROUPS="
    +
    str(
        len(
            production_group_ids
        )
    )
)

print(
    "V1_PURCHASE_FIELDS_MUTATED="
    +
    str(
        purchase_field_mutations
    )
)

print(
    "BUY_CANDIDATE_NOW="
    +
    str(
        buy_count
    )
)

print(
    "REVIEW_GLOBAL_COMPARABLE_ONLY="
    +
    str(
        review_count
    )
)

print(
    "WAIT_FOR_Q10_ENTRY="
    +
    str(
        wait_count
    )
)

print(
    "PURCHASE_RECOMMENDATIONS_CHANGED_DUE_TO_V1_1_RANKING=0"
)

print(
    "PURCHASE_POLICY_REDESIGNED=FALSE"
)

print(
    "POINT_FORECAST_REBUILT=FALSE"
)

print(
    "MONTE_CARLO_REBUILT=FALSE"
)

print(
    "Q10_RECALCULATED=FALSE"
)

print(
    "AUTOMATIC_PURCHASE_EXECUTION=FALSE"
)

print(
    "NEXT_GATE=SL8G_SECRET_LAIR_V1_1_FINAL_CLOSEOUT"
)