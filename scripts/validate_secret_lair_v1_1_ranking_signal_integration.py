from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


APPENDED_FIELDS = {
    "v1_original_competition_rank",
    "v1_original_rank_group_index",
    "v1_original_rank_group_size",
    "v1_1_candidate_competition_rank",
    "v1_1_candidate_rank_group_index",
    "v1_1_candidate_rank_group_size",
    "v1_1_candidate_co_ranked_tie",
    "latest_interval_momentum",
    "recent_minus_median_momentum",
    "signal_complete_for_original_group",
    "original_group_refined",
    "ranking_primary_authority_preserved",
    "ranking_signal_method",
    "weighted_ranking_score_used_v1_1",
    "current_price_used_as_signal_tiebreak",
    "product_id_or_name_used_as_signal_tiebreak",
}


def fail(message: str) -> None:
    raise RuntimeError(
        "FAIL-CLOSED: " + message
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def truth(value: object) -> bool:
    text = clean(value).lower()

    if text == "true":
        return True

    if text == "false":
        return False

    fail(
        "invalid boolean value: "
        + clean(value)
    )


def finite(value: object) -> float | None:
    text = clean(value)

    if not text:
        return None

    result = float(text)

    if not math.isfinite(result):
        return None

    return result


def read_csv(path: Path) -> tuple[
    list[str],
    list[dict[str, str]],
]:

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


parser = argparse.ArgumentParser()

parser.add_argument("--v1-ranking", required=True)
parser.add_argument("--candidate", required=True)
parser.add_argument("--run-root", required=True)

args = parser.parse_args()


v1_fields, v1_rows = read_csv(
    Path(args.v1_ranking)
)

candidate_fields, candidate_rows = read_csv(
    Path(args.candidate)
)


if not v1_rows:
    fail("V1 ranking empty")

if not candidate_rows:
    fail("candidate ranking empty")


# ---------------------------------------------------------------------------
# 1. Schema preservation
# ---------------------------------------------------------------------------

missing_v1_fields = [
    field
    for field in v1_fields
    if field not in candidate_fields
]


if missing_v1_fields:
    fail(
        "candidate dropped V1 fields: "
        + ",".join(missing_v1_fields)
    )


unexpected_appended = [
    field
    for field in candidate_fields
    if (
        field not in v1_fields
        and
        field not in APPENDED_FIELDS
    )
]


if unexpected_appended:
    fail(
        "unexpected candidate fields: "
        + ",".join(unexpected_appended)
    )


# ---------------------------------------------------------------------------
# 2. Universe identity
# ---------------------------------------------------------------------------

def index_by_product(
    rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:

    indexed: dict[
        str,
        dict[str, str]
    ] = {}

    for row in rows:

        product_id = clean(
            row.get(
                "secret_lair_id"
            )
        )

        if not product_id:
            fail("blank Secret Lair identity")

        if product_id in indexed:
            fail(
                "duplicate Secret Lair identity: "
                + product_id
            )

        indexed[product_id] = row

    return indexed


v1_by_product = index_by_product(v1_rows)
candidate_by_product = index_by_product(candidate_rows)


if set(v1_by_product) != set(candidate_by_product):

    missing = sorted(
        set(v1_by_product)
        -
        set(candidate_by_product)
    )

    extra = sorted(
        set(candidate_by_product)
        -
        set(v1_by_product)
    )

    fail(
        "candidate universe drift; "
        f"missing={len(missing)}; "
        f"extra={len(extra)}"
    )


# ---------------------------------------------------------------------------
# 3. Every certified V1 field must be byte-string equivalent by product.
# ---------------------------------------------------------------------------

v1_field_mutations = 0


for product_id in sorted(v1_by_product):

    original = v1_by_product[
        product_id
    ]

    candidate = candidate_by_product[
        product_id
    ]

    for field in v1_fields:

        if clean(
            original.get(field)
        ) != clean(
            candidate.get(field)
        ):

            v1_field_mutations += 1


if v1_field_mutations != 0:

    fail(
        "certified V1 field mutation count="
        + str(v1_field_mutations)
    )


# ---------------------------------------------------------------------------
# 4. Group validation
# ---------------------------------------------------------------------------

v1_groups: dict[
    int,
    list[dict[str, str]]
] = {}


for row in v1_rows:

    group = int(
        clean(
            row.get(
                "rank_group_index"
            )
        )
    )

    v1_groups.setdefault(
        group,
        [],
    ).append(
        row
    )


validation_rows: list[
    dict[str, object]
] = []


cross_group_violations = 0
non_tie_refinement_violations = 0
missing_group_preservation_violations = 0
lexicographic_order_violations = 0
identical_pair_tie_violations = 0
candidate_group_size_violations = 0
candidate_competition_rank_violations = 0
hidden_mechanism_violations = 0

refined_groups = 0
preserved_incomplete_groups = 0
refined_products = 0
remaining_tied_products = 0


prior_original_group_max_candidate_position = 0


for original_group_index in sorted(v1_groups):

    originals = v1_groups[
        original_group_index
    ]

    candidates = [
        candidate_by_product[
            clean(
                row[
                    "secret_lair_id"
                ]
            )
        ]
        for row in originals
    ]

    candidates_sorted = sorted(
        candidates,
        key=lambda row: (
            int(
                clean(
                    row[
                        "v1_1_candidate_competition_rank"
                    ]
                )
            ),
            int(
                clean(
                    row[
                        "v1_1_candidate_rank_group_index"
                    ]
                )
            ),
        ),
    )

    original_size = len(
        originals
    )

    refined_flags = {
        truth(
            row[
                "original_group_refined"
            ]
        )
        for row
        in candidates
    }

    complete_flags = {
        truth(
            row[
                "signal_complete_for_original_group"
            ]
        )
        for row
        in candidates
    }

    if len(refined_flags) != 1:
        fail(
            "inconsistent refinement state inside V1 group "
            + str(original_group_index)
        )

    if len(complete_flags) != 1:
        fail(
            "inconsistent signal-completeness state inside V1 group "
            + str(original_group_index)
        )

    refined = next(
        iter(
            refined_flags
        )
    )

    complete = next(
        iter(
            complete_flags
        )
    )

    candidate_group_ids = sorted(
        {
            int(
                clean(
                    row[
                        "v1_1_candidate_rank_group_index"
                    ]
                )
            )
            for row
            in candidates
        }
    )

    candidate_rank_values = [
        int(
            clean(
                row[
                    "v1_1_candidate_competition_rank"
                ]
            )
        )
        for row
        in candidates
    ]

    group_min_rank = min(
        candidate_rank_values
    )

    group_max_rank = max(
        candidate_rank_values
    )

    if (
        group_min_rank
        <=
        prior_original_group_max_candidate_position
    ):
        cross_group_violations += 1

    prior_original_group_max_candidate_position = (
        group_max_rank
    )

    if (
        original_size == 1
        and
        refined
    ):
        non_tie_refinement_violations += 1

    if (
        original_size > 1
        and
        not complete
    ):

        preserved_incomplete_groups += 1

        if refined:
            missing_group_preservation_violations += 1

        if len(candidate_group_ids) != 1:
            missing_group_preservation_violations += 1

    if refined:

        refined_groups += 1
        refined_products += original_size

        signal_sequence: list[
            tuple[float, float]
        ] = []

        previous_pair: tuple[
            float,
            float
        ] | None = None

        previous_group_id: int | None = None

        for row in candidates_sorted:

            latest = finite(
                row[
                    "latest_interval_momentum"
                ]
            )

            recent = finite(
                row[
                    "recent_minus_median_momentum"
                ]
            )

            if (
                latest is None
                or
                recent is None
            ):
                lexicographic_order_violations += 1
                continue

            pair = (
                latest,
                recent,
            )

            signal_sequence.append(
                pair
            )

            current_group_id = int(
                clean(
                    row[
                        "v1_1_candidate_rank_group_index"
                    ]
                )
            )

            if previous_pair is not None:

                if pair > previous_pair:
                    lexicographic_order_violations += 1

                if (
                    pair == previous_pair
                    and
                    current_group_id
                    !=
                    previous_group_id
                ):
                    identical_pair_tie_violations += 1

                if (
                    pair != previous_pair
                    and
                    current_group_id
                    ==
                    previous_group_id
                ):
                    identical_pair_tie_violations += 1

            previous_pair = pair
            previous_group_id = current_group_id

    # -----------------------------------------------------------------------
    # Candidate subgroup size declarations must match actual memberships.
    # -----------------------------------------------------------------------

    actual_subgroup_counts: dict[
        int,
        int
    ] = {}

    for row in candidates:

        subgroup_id = int(
            clean(
                row[
                    "v1_1_candidate_rank_group_index"
                ]
            )
        )

        actual_subgroup_counts[
            subgroup_id
        ] = (
            actual_subgroup_counts.get(
                subgroup_id,
                0,
            )
            +
            1
        )

    for row in candidates:

        subgroup_id = int(
            clean(
                row[
                    "v1_1_candidate_rank_group_index"
                ]
            )
        )

        declared_size = int(
            clean(
                row[
                    "v1_1_candidate_rank_group_size"
                ]
            )
        )

        if (
            declared_size
            !=
            actual_subgroup_counts[
                subgroup_id
            ]
        ):
            candidate_group_size_violations += 1

        declared_tie = truth(
            row[
                "v1_1_candidate_co_ranked_tie"
            ]
        )

        if (
            declared_tie
            !=
            (
                declared_size > 1
            )
        ):
            candidate_group_size_violations += 1

        if declared_size > 1:
            remaining_tied_products += 1

        if truth(
            row[
                "weighted_ranking_score_used_v1_1"
            ]
        ):
            hidden_mechanism_violations += 1

        if truth(
            row[
                "current_price_used_as_signal_tiebreak"
            ]
        ):
            hidden_mechanism_violations += 1

        if truth(
            row[
                "product_id_or_name_used_as_signal_tiebreak"
            ]
        ):
            hidden_mechanism_violations += 1

        if not truth(
            row[
                "ranking_primary_authority_preserved"
            ]
        ):
            hidden_mechanism_violations += 1

    # -----------------------------------------------------------------------
    # Competition rank semantics inside each original V1 group.
    #
    # Subgroups should occupy contiguous positions.
    # -----------------------------------------------------------------------

    ordered_subgroups = sorted(
        actual_subgroup_counts
    )

    expected_rank = group_min_rank

    for subgroup_id in ordered_subgroups:

        subgroup_rows = [
            row
            for row
            in candidates
            if int(
                clean(
                    row[
                        "v1_1_candidate_rank_group_index"
                    ]
                )
            )
            ==
            subgroup_id
        ]

        subgroup_ranks = {
            int(
                clean(
                    row[
                        "v1_1_candidate_competition_rank"
                    ]
                )
            )
            for row
            in subgroup_rows
        }

        if subgroup_ranks != {
            expected_rank
        }:
            candidate_competition_rank_violations += 1

        expected_rank += len(
            subgroup_rows
        )

    validation_rows.append(
        {
            "v1_original_rank_group_index":
                original_group_index,

            "v1_original_group_size":
                original_size,

            "signal_complete":
                complete,

            "candidate_refined":
                refined,

            "candidate_subgroup_count":
                len(
                    actual_subgroup_counts
                ),

            "candidate_min_competition_rank":
                group_min_rank,

            "candidate_max_competition_rank":
                group_max_rank,

            "validation_pass":
                True,
        }
    )


# ---------------------------------------------------------------------------
# 5. Global candidate rank-group integrity.
# ---------------------------------------------------------------------------

candidate_groups: dict[
    int,
    list[dict[str, str]]
] = {}


for row in candidate_rows:

    group_id = int(
        clean(
            row[
                "v1_1_candidate_rank_group_index"
            ]
        )
    )

    candidate_groups.setdefault(
        group_id,
        [],
    ).append(
        row
    )


candidate_group_ids = sorted(
    candidate_groups
)


if candidate_group_ids != list(
    range(
        1,
        len(candidate_group_ids) + 1,
    )
):

    fail(
        "candidate rank-group indices are not contiguous"
    )


all_violation_counts = {
    "cross_group":
        cross_group_violations,

    "non_tie_refinement":
        non_tie_refinement_violations,

    "missing_group_preservation":
        missing_group_preservation_violations,

    "lexicographic_order":
        lexicographic_order_violations,

    "identical_pair_tie":
        identical_pair_tie_violations,

    "candidate_group_size":
        candidate_group_size_violations,

    "candidate_competition_rank":
        candidate_competition_rank_violations,

    "hidden_mechanism":
        hidden_mechanism_violations,
}


total_violations = sum(
    all_violation_counts.values()
)


if total_violations != 0:

    fail(
        "ranking integration validation violations: "
        +
        json.dumps(
            all_violation_counts,
            sort_keys=True,
        )
    )


# ---------------------------------------------------------------------------
# 6. Cross-check expected certified diagnostics.
# ---------------------------------------------------------------------------

diagnostics = {
    "ranked_products":
        len(candidate_rows),

    "original_rank_groups":
        len(v1_groups),

    "original_tied_groups":
        sum(
            1
            for members
            in v1_groups.values()
            if len(members) > 1
        ),

    "original_tied_products":
        sum(
            len(members)
            for members
            in v1_groups.values()
            if len(members) > 1
        ),

    "groups_refined":
        refined_groups,

    "products_in_refined_groups":
        refined_products,

    "groups_preserved_for_missing_signal":
        preserved_incomplete_groups,

    "candidate_rank_groups":
        len(candidate_groups),

    "remaining_tied_products":
        remaining_tied_products,
}


summary = {
    "status":
        "SECRET_LAIR_V1_1_RANKING_SIGNAL_INTEGRATION_VALIDATION_COMPLETE",

    "diagnostics":
        diagnostics,

    "violations":
        all_violation_counts,

    "total_violations":
        total_violations,

    "validation": {
        "exact_V1_product_universe_preserved":
            True,

        "all_V1_fields_preserved":
            True,

        "cross_V1_group_reordering":
            False,

        "only_existing_V1_ties_refined":
            True,

        "incomplete_signal_groups_preserved":
            True,

        "lexicographic_signal_order_verified":
            True,

        "identical_signal_pairs_preserve_ties":
            True,

        "candidate_group_sizes_verified":
            True,

        "competition_ranks_verified":
            True,

        "hidden_tie_break_mechanism_detected":
            False,

        "weighted_score_used":
            False,

        "current_price_tie_break_used":
            False,

        "identity_tie_break_used":
            False,
    },

    "governance": {
        "forecast_changed":
            False,

        "Monte_Carlo_changed":
            False,

        "purchase_recommendation_changed":
            False,

        "production_ranking_promoted_in_this_stage":
            False,

        "automatic_purchase_execution":
            False,
    },

    "result":
        "RANKING_SIGNAL_INTEGRATION_VALIDATED_FOR_PRODUCTION_PROMOTION",

    "next_gate":
        "SL8F_SECRET_LAIR_V1_1_PRODUCTION_RANKING_PROMOTION_AND_PURCHASE_RECONCILIATION",
}


run_root = Path(
    args.run_root
)


ledger_path = (
    run_root
    /
    "secret_lair_v1_1_ranking_signal_integration_validation.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_1_ranking_signal_integration_validation_summary.json"
)


write_csv(
    ledger_path,
    validation_rows,
    [
        "v1_original_rank_group_index",
        "v1_original_group_size",
        "signal_complete",
        "candidate_refined",
        "candidate_subgroup_count",
        "candidate_min_competition_rank",
        "candidate_max_competition_rank",
        "validation_pass",
    ],
)


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_V1_1_RANKING_SIGNAL_INTEGRATION_VALIDATION=PASS"
)

for key, value in diagnostics.items():

    print(
        key.upper()
        +
        "="
        +
        str(value)
    )


print(
    "TOTAL_VALIDATION_VIOLATIONS="
    +
    str(total_violations)
)

print(
    "ALL_V1_FIELDS_PRESERVED=TRUE"
)

print(
    "CROSS_V1_GROUP_REORDERING=FALSE"
)

print(
    "LEXICOGRAPHIC_SIGNAL_ORDER_VERIFIED=TRUE"
)

print(
    "INCOMPLETE_SIGNAL_GROUPS_PRESERVED=TRUE"
)

print(
    "IDENTICAL_SIGNAL_PAIRS_PRESERVE_TIES=TRUE"
)

print(
    "HIDDEN_TIE_BREAK_MECHANISM_DETECTED=FALSE"
)

print(
    "PRODUCTION_RANKING_PROMOTED_IN_THIS_STAGE=FALSE"
)

print(
    "NEXT_GATE="
    +
    summary[
        "next_gate"
    ]
)