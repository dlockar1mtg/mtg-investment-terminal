from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


LATEST = "latest_interval_annualized_log_return"
RECENT = "latest_minus_median_interval_annualized_log_return"


def fail(message: str) -> None:
    raise RuntimeError("FAIL-CLOSED: " + message)


def clean(value: object) -> str:
    return str(value or "").strip()


def finite(value: object) -> float | None:
    text = clean(value)

    if not text:
        return None

    try:
        result = float(text)
    except ValueError:
        return None

    if not math.isfinite(result):
        return None

    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


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

parser.add_argument("--ranking", required=True)
parser.add_argument("--foundation", required=True)
parser.add_argument("--run-root", required=True)

args = parser.parse_args()


ranking = read_csv(Path(args.ranking))
foundation = read_csv(Path(args.foundation))


if not ranking:
    fail("V1 ranking is empty")

if not foundation:
    fail("V1.1 feature foundation is empty")


features: dict[str, dict[str, object]] = {}


for row in foundation:

    product_id = clean(
        row.get("secret_lair_id")
    )

    if not product_id:
        fail("blank product identity in feature foundation")

    if product_id in features:
        fail(
            "duplicate product identity in feature foundation: "
            + product_id
        )

    features[product_id] = {
        "latest":
            finite(
                row.get(LATEST)
            ),

        "recent":
            finite(
                row.get(RECENT)
            ),
    }


rank_groups: dict[int, list[dict[str, str]]] = {}


for row in ranking:

    product_id = clean(
        row.get("secret_lair_id")
    )

    if not product_id:
        fail("blank product identity in V1 ranking")

    rank_group = int(
        clean(
            row.get("rank_group_index")
        )
    )

    row["_product_id"] = product_id

    rank_groups.setdefault(
        rank_group,
        [],
    ).append(row)


group_order = sorted(rank_groups)


candidate_rows: list[dict[str, object]] = []

groups_refined = 0
products_in_refined_groups = 0
groups_preserved_for_missing_signal = 0
products_preserved_for_missing_signal = 0
original_tied_groups = 0
original_tied_products = 0
remaining_tied_groups = 0
remaining_tied_products = 0

global_position = 1
candidate_group_index = 0


for original_group_index in group_order:

    members = rank_groups[
        original_group_index
    ]

    original_group_size = len(members)

    if original_group_size > 1:
        original_tied_groups += 1
        original_tied_products += original_group_size

    enriched: list[
        tuple[
            dict[str, str],
            float | None,
            float | None,
        ]
    ] = []

    all_complete = True

    for row in members:

        product_id = row["_product_id"]

        feature = features.get(
            product_id
        )

        if feature is None:
            latest = None
            recent = None
        else:
            latest = feature["latest"]
            recent = feature["recent"]

        if (
            latest is None
            or
            recent is None
        ):
            all_complete = False

        enriched.append(
            (
                row,
                latest,
                recent,
            )
        )

    refine = (
        original_group_size > 1
        and
        all_complete
    )

    if refine:

        groups_refined += 1
        products_in_refined_groups += original_group_size

        ordered = sorted(
            enriched,
            key=lambda item: (
                -float(item[1]),
                -float(item[2]),
            ),
        )

        subgroups: list[
            list[
                tuple[
                    dict[str, str],
                    float | None,
                    float | None,
                ]
            ]
        ] = []

        for item in ordered:

            signature = (
                float(item[1]),
                float(item[2]),
            )

            if not subgroups:
                subgroups.append([item])
                continue

            prior = subgroups[-1][0]

            prior_signature = (
                float(prior[1]),
                float(prior[2]),
            )

            if signature == prior_signature:
                subgroups[-1].append(item)
            else:
                subgroups.append([item])

    else:

        if (
            original_group_size > 1
            and
            not all_complete
        ):
            groups_preserved_for_missing_signal += 1
            products_preserved_for_missing_signal += original_group_size

        subgroups = [
            enriched
        ]

    for subgroup in subgroups:

        candidate_group_index += 1

        subgroup_size = len(
            subgroup
        )

        candidate_rank = global_position

        if subgroup_size > 1:
            remaining_tied_groups += 1
            remaining_tied_products += subgroup_size

        for row, latest, recent in subgroup:

            output = {
                key: value
                for key, value
                in row.items()
                if not key.startswith("_")
            }

            output[
                "v1_original_competition_rank"
            ] = int(
                clean(
                    row.get(
                        "competition_rank"
                    )
                )
            )

            output[
                "v1_original_rank_group_index"
            ] = int(
                clean(
                    row.get(
                        "rank_group_index"
                    )
                )
            )

            output[
                "v1_original_rank_group_size"
            ] = original_group_size

            output[
                "v1_1_candidate_competition_rank"
            ] = candidate_rank

            output[
                "v1_1_candidate_rank_group_index"
            ] = candidate_group_index

            output[
                "v1_1_candidate_rank_group_size"
            ] = subgroup_size

            output[
                "v1_1_candidate_co_ranked_tie"
            ] = (
                subgroup_size > 1
            )

            output[
                "latest_interval_momentum"
            ] = (
                ""
                if latest is None
                else latest
            )

            output[
                "recent_minus_median_momentum"
            ] = (
                ""
                if recent is None
                else recent
            )

            output[
                "signal_complete_for_original_group"
            ] = all_complete

            output[
                "original_group_refined"
            ] = refine

            output[
                "ranking_primary_authority_preserved"
            ] = True

            output[
                "ranking_signal_method"
            ] = (
                "WITHIN_V1_TIE_ONLY_LEXICOGRAPHIC_MOMENTUM"
                if refine
                else
                "V1_GROUP_PRESERVED"
            )

            output[
                "weighted_ranking_score_used_v1_1"
            ] = False

            output[
                "current_price_used_as_signal_tiebreak"
            ] = False

            output[
                "product_id_or_name_used_as_signal_tiebreak"
            ] = False

            candidate_rows.append(
                output
            )

        global_position += subgroup_size


if len(candidate_rows) != len(ranking):
    fail("candidate ranking row count drift")


# ---------------------------------------------------------------------------
# Verify no cross-V1-group inversion.
# ---------------------------------------------------------------------------

prior_original_group = None
prior_candidate_max = 0


for original_group_index in group_order:

    rows_for_group = [
        row
        for row
        in candidate_rows
        if int(
            row[
                "v1_original_rank_group_index"
            ]
        )
        ==
        original_group_index
    ]

    ranks = [
        int(
            row[
                "v1_1_candidate_competition_rank"
            ]
        )
        for row
        in rows_for_group
    ]

    group_min = min(ranks)
    group_max = max(ranks)

    if (
        prior_original_group is not None
        and
        group_min <= prior_candidate_max
    ):
        fail(
            "cross-V1-rank-group inversion detected"
        )

    prior_original_group = original_group_index
    prior_candidate_max = group_max


summary = {
    "status":
        "SECRET_LAIR_V1_1_RANKING_SIGNAL_INTEGRATION_CANDIDATE_COMPLETE",

    "ranked_products":
        len(candidate_rows),

    "original_rank_groups":
        len(rank_groups),

    "original_tied_groups":
        original_tied_groups,

    "original_tied_products":
        original_tied_products,

    "groups_refined":
        groups_refined,

    "products_in_refined_groups":
        products_in_refined_groups,

    "groups_preserved_for_missing_signal":
        groups_preserved_for_missing_signal,

    "products_preserved_for_missing_signal":
        products_preserved_for_missing_signal,

    "candidate_rank_groups":
        candidate_group_index,

    "remaining_tied_groups":
        remaining_tied_groups,

    "remaining_tied_products":
        remaining_tied_products,

    "governance": {
        "V1_rank_group_order_preserved":
            True,

        "cross_V1_group_reordering":
            False,

        "refinement_scope":
            "WITHIN_EXISTING_V1_TIE_GROUPS_ONLY",

        "all_group_members_require_both_signals":
            True,

        "primary_signal":
            "LATEST_INTERVAL_MOMENTUM",

        "secondary_signal":
            "RECENT_MINUS_MEDIAN_MOMENTUM",

        "weighted_score":
            False,

        "current_price_tie_break":
            False,

        "product_identity_tie_break":
            False,

        "forecast_changed":
            False,

        "Monte_Carlo_changed":
            False,

        "production_ranking_created":
            False,

        "purchase_recommendation_changed":
            False,

        "automatic_purchase_execution":
            False,
    },

    "next_gate":
        "SL8E_SECRET_LAIR_V1_1_RANKING_SIGNAL_INTEGRATION_VALIDATION",
}


run_root = Path(
    args.run_root
)


candidate_path = (
    run_root
    /
    "secret_lair_v1_1_ranking_signal_integration_candidate.csv"
)

summary_path = (
    run_root
    /
    "secret_lair_v1_1_ranking_signal_integration_summary.json"
)


write_csv(
    candidate_path,
    candidate_rows,
    list(
        candidate_rows[0].keys()
    ),
)


summary_path.write_text(
    json.dumps(
        summary,
        indent=2,
    ),
    encoding="utf-8",
)


print(
    "SECRET_LAIR_V1_1_RANKING_SIGNAL_INTEGRATION=PASS"
)

for key in (
    "ranked_products",
    "original_rank_groups",
    "original_tied_groups",
    "original_tied_products",
    "groups_refined",
    "products_in_refined_groups",
    "groups_preserved_for_missing_signal",
    "products_preserved_for_missing_signal",
    "candidate_rank_groups",
    "remaining_tied_groups",
    "remaining_tied_products",
):

    print(
        key.upper()
        +
        "="
        +
        str(
            summary[key]
        )
    )


print(
    "CROSS_V1_GROUP_REORDERING=FALSE"
)

print(
    "WEIGHTED_RANKING_SCORE=FALSE"
)

print(
    "PRODUCTION_RANKING_CREATED=FALSE"
)

print(
    "NEXT_GATE="
    +
    summary["next_gate"]
)