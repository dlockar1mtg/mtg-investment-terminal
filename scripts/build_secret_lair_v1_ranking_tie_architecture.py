from __future__ import annotations

import argparse
import csv
import json
import math

from collections import Counter, defaultdict
from pathlib import Path


ESTABLISHED = (
    "ESTABLISHED_1Y_TOURNAMENT_CANDIDATE"
)

SHORT_HISTORY = (
    "SHORT_HISTORY_TOURNAMENT_CANDIDATE"
)

CURRENT_ONLY = (
    "CURRENT_PRICE_ONLY_NEW_PRODUCT_CANDIDATE"
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
    "--audit",
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

args = parser.parse_args()

audit_rows = read_csv(
    Path(
        args.audit
    )
)

run_root = Path(
    args.run_root
)

run_root.mkdir(
    parents=True,
    exist_ok=True,
)


if len(audit_rows) != args.expected_products:
    fail(
        "ranking architecture population drift: "
        f"expected={args.expected_products}, "
        f"actual={len(audit_rows)}"
    )


product_ids: set[str] = set()

architecture_rows: list[
    dict[str, object]
] = []

signature_members: dict[
    str,
    list[str],
] = defaultdict(list)


# ---------------------------------------------------------------------------
# Evidence hierarchy
#
# IMPORTANT:
#
# This is NOT a weighted score.
#
# Primary investment signal:
#     certified central 1Y modeled return.
#
# Within an IDENTICAL modeled return profile only:
#
#     1. own-history evidence state
#     2. exact structural comparable support
#     3. history span
#     4. historical observation count
#     5. exact comparable event count
#     6. global comparable event count
#
# Remaining identical tuples remain genuinely tied.
#
# No:
#     MC seed
#     MC sample metric
#     current dollar price
#     alphabetical order
#     product ID
# may break an economic/evidence tie.
# ---------------------------------------------------------------------------


for row in audit_rows:

    product_id = clean(
        row.get(
            "secret_lair_id"
        )
    )

    if not product_id:
        fail(
            "blank Secret Lair identity"
        )

    if product_id in product_ids:
        fail(
            "duplicate Secret Lair identity: "
            + product_id
        )

    product_ids.add(
        product_id
    )


    method_class = clean(
        row.get(
            "modeling_method_class"
        )
    )

    central_return = parse_float(
        row.get(
            "central_1y_log_return"
        )
    )


    # ---------------------------------------------------------------
    # Evidence state.
    #
    # Ordinal values exist only so the deterministic lexicographic
    # implementation can sort the categorical evidence states.
    #
    # They are NOT additive scores and are never summed.
    # ---------------------------------------------------------------

    if method_class == ESTABLISHED:

        own_history_evidence_class = (
            "ESTABLISHED_DIRECT_HISTORY"
        )

        own_history_ordinal = 2

    elif method_class == SHORT_HISTORY:

        own_history_evidence_class = (
            "SHORT_DIRECT_HISTORY"
        )

        own_history_ordinal = 1

    elif method_class == CURRENT_ONLY:

        own_history_evidence_class = (
            "NO_DIRECT_HISTORY_CURRENT_PRICE_ONLY"
        )

        own_history_ordinal = 0

    else:

        fail(
            "unexpected forecastable modeling class: "
            + method_class
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

    history_observations = parse_int(
        row.get(
            "historical_observation_count"
        )
    )

    history_span = parse_int(
        row.get(
            "history_span_days"
        )
    )

    exact_support = (
        exact_peer_count > 0
        and
        exact_event_count > 0
    )

    exact_support_ordinal = (
        1
        if exact_support
        else 0
    )


    underlying_return_profile = clean(
        row.get(
            "underlying_risk_signature"
        )
    )

    if not underlying_return_profile:
        fail(
            "missing underlying return profile: "
            + product_id
        )


    # Evidence signature applies INSIDE a shared return profile.
    #
    # No product ID is included.
    # Therefore truly identical evidence remains tied.

    evidence_signature = "|".join(
        (
            str(
                own_history_ordinal
            ),
            str(
                exact_support_ordinal
            ),
            str(
                history_span
            ),
            str(
                history_observations
            ),
            str(
                exact_event_count
            ),
            str(
                global_event_count
            ),
        )
    )


    full_tie_signature = (
        underlying_return_profile
        + "|EVIDENCE|"
        + evidence_signature
    )

    signature_members[
        full_tie_signature
    ].append(
        product_id
    )


    architecture_rows.append(
        {
            "secret_lair_id":
                product_id,

            "product_name":
                clean(
                    row.get(
                        "product_name"
                    )
                ),

            "modeling_method_class":
                method_class,

            "production_method":
                clean(
                    row.get(
                        "production_method"
                    )
                ),

            "central_1y_log_return":
                central_return,

            "underlying_return_profile":
                underlying_return_profile,

            "own_history_evidence_class":
                own_history_evidence_class,

            "own_history_ordinal_for_lexicographic_sort_only":
                own_history_ordinal,

            "exact_structural_comparable_support":
                exact_support,

            "exact_support_ordinal_for_lexicographic_sort_only":
                exact_support_ordinal,

            "history_span_days":
                history_span,

            "historical_observation_count":
                history_observations,

            "exact_structural_comparable_product_count":
                exact_peer_count,

            "global_comparable_product_count":
                global_peer_count,

            "exact_structural_comparable_event_count":
                exact_event_count,

            "global_comparable_event_count":
                global_event_count,

            "evidence_tie_signature":
                evidence_signature,

            "full_ranking_tie_signature":
                full_tie_signature,

            "ranking_weighted_score":
                "",

            "ranking_weights_used":
                False,

            "monte_carlo_seed_used_for_order":
                False,

            "monte_carlo_sample_metric_used_for_tie_break":
                False,

            "current_price_used_for_quality_order":
                False,

            "secret_lair_id_used_for_tie_break":
                False,

            "product_name_used_for_tie_break":
                False,

            "final_rank_created":
                False,

            "purchase_recommendation_created":
                False,
        }
    )


# ---------------------------------------------------------------------------
# Populate tie-group sizes.
# ---------------------------------------------------------------------------

for row in architecture_rows:

    signature = str(
        row[
            "full_ranking_tie_signature"
        ]
    )

    row[
        "products_sharing_full_ranking_tie_signature"
    ] = len(
        signature_members[
            signature
        ]
    )

    row[
        "ranking_tie_must_be_preserved_if_signature_identical"
    ] = True


unique_full_signatures = len(
    signature_members
)

products_in_remaining_ties = sum(
    len(members)
    for members
    in signature_members.values()
    if len(members) > 1
)

largest_remaining_tie = max(
    len(members)
    for members
    in signature_members.values()
)

products_unique_after_evidence = sum(
    1
    for row
    in architecture_rows
    if int(
        row[
            "products_sharing_full_ranking_tie_signature"
        ]
    ) == 1
)


method_class_counts = Counter(
    row[
        "modeling_method_class"
    ]
    for row
    in architecture_rows
)


output_path = (
    run_root
    /
    "secret_lair_v1_ranking_signal_and_tie_architecture.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_ranking_signal_and_tie_summary.json"
)


write_csv(
    output_path,
    architecture_rows,
    [
        "secret_lair_id",
        "product_name",
        "modeling_method_class",
        "production_method",
        "central_1y_log_return",
        "underlying_return_profile",
        "own_history_evidence_class",
        "own_history_ordinal_for_lexicographic_sort_only",
        "exact_structural_comparable_support",
        "exact_support_ordinal_for_lexicographic_sort_only",
        "history_span_days",
        "historical_observation_count",
        "exact_structural_comparable_product_count",
        "global_comparable_product_count",
        "exact_structural_comparable_event_count",
        "global_comparable_event_count",
        "evidence_tie_signature",
        "full_ranking_tie_signature",
        "products_sharing_full_ranking_tie_signature",
        "ranking_tie_must_be_preserved_if_signature_identical",
        "ranking_weighted_score",
        "ranking_weights_used",
        "monte_carlo_seed_used_for_order",
        "monte_carlo_sample_metric_used_for_tie_break",
        "current_price_used_for_quality_order",
        "secret_lair_id_used_for_tie_break",
        "product_name_used_for_tie_break",
        "final_rank_created",
        "purchase_recommendation_created",
    ],
)


summary = {
    "status":
        "SECRET_LAIR_V1_RANKING_SIGNAL_AND_TIE_ARCHITECTURE_COMPLETE",

    "products":
        len(
            architecture_rows
        ),

    "method_class_counts":
        dict(
            method_class_counts
        ),

    "ranking_architecture": {
        "primary_signal":
            "CERTIFIED_CENTRAL_1Y_MODELED_RETURN",

        "secondary_scope":
            "WITHIN_IDENTICAL_UNDERLYING_RETURN_PROFILE_ONLY",

        "secondary_method":
            "LEXICOGRAPHIC_GOVERNED_EVIDENCE_HIERARCHY",

        "secondary_sequence": [
            "OWN_HISTORY_EVIDENCE_CLASS",
            "EXACT_STRUCTURAL_COMPARABLE_SUPPORT",
            "HISTORY_SPAN_DAYS",
            "HISTORICAL_OBSERVATION_COUNT",
            "EXACT_STRUCTURAL_COMPARABLE_EVENT_COUNT",
            "GLOBAL_COMPARABLE_EVENT_COUNT",
        ],

        "weighted_score":
            False,

        "arbitrary_weights":
            False,

        "precollector_weights_reused":
            False,

        "remaining_identical_tuples_are_ties":
            True,

        "monte_carlo_seed_tie_break":
            False,

        "monte_carlo_sample_metric_tie_break":
            False,

        "current_price_quality_tie_break":
            False,

        "product_id_tie_break":
            False,

        "product_name_tie_break":
            False,
    },

    "tie_resolution": {
        "unique_full_ranking_signatures":
            unique_full_signatures,

        "products_unique_after_evidence":
            products_unique_after_evidence,

        "products_remaining_in_genuine_ties":
            products_in_remaining_ties,

        "largest_remaining_genuine_tie":
            largest_remaining_tie,
    },

    "authorization": {
        "ranking_architecture_certified":
            True,

        "ranking_execution":
            True,

        "co_ranked_ties_allowed":
            True,

        "ranking_certified":
            False,

        "purchase_analysis":
            False,

        "purchase_recommendation":
            False,
    },

    "next_gate":
        "SL6B_SECRET_LAIR_RANKING_EXECUTION",
}


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_RANKING_SIGNAL_ARCHITECTURE=PASS"
)

print(
    "PRODUCTS="
    + str(
        len(
            architecture_rows
        )
    )
)

print(
    "PRIMARY_SIGNAL=CERTIFIED_CENTRAL_1Y_MODELED_RETURN"
)

print(
    "SECONDARY_METHOD=LEXICOGRAPHIC_GOVERNED_EVIDENCE_HIERARCHY"
)

print(
    "RANKING_WEIGHTS_USED=FALSE"
)

print(
    "PRECOLLECTOR_WEIGHTS_REUSED=FALSE"
)

print(
    "UNIQUE_FULL_RANKING_SIGNATURES="
    + str(
        unique_full_signatures
    )
)

print(
    "PRODUCTS_UNIQUE_AFTER_EVIDENCE="
    + str(
        products_unique_after_evidence
    )
)

print(
    "PRODUCTS_REMAINING_IN_GENUINE_TIES="
    + str(
        products_in_remaining_ties
    )
)

print(
    "LARGEST_REMAINING_GENUINE_TIE="
    + str(
        largest_remaining_tie
    )
)

print(
    "MONTE_CARLO_SEED_TIE_BREAK=FALSE"
)

print(
    "CURRENT_PRICE_QUALITY_TIE_BREAK=FALSE"
)

print(
    "PRODUCT_ID_TIE_BREAK=FALSE"
)

print(
    "GENUINE_TIES_PRESERVED=TRUE"
)

print(
    "RANKING_EXECUTION_AUTHORIZED=TRUE"
)

print(
    "RANKING_CERTIFIED=FALSE"
)

print(
    "PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE"
)

print(
    "NEXT_GATE=SL6B_SECRET_LAIR_RANKING_EXECUTION"
)