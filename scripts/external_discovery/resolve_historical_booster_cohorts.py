from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

POLICY_PATH = (
    ROOT
    / "config"
    / "historical_booster_candidate_policy.yaml"
)

CANDIDATE_LANE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
    / "historical_booster_review_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_cohort_policy"
)

SCHEMA_VERSION = "10.5R.1D.2.3C.1"

OUTPUT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_type",
    "canonical_packaging_level",
    "prior_candidate_review_lane",
    "governed_candidate_cohort",
    "cohort_reason",
    "specialty_basis",
    "price_review_state",
    "price_source_type",
    "market_price",
    "current_price_candidate",
    "release_timing_state",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def load_policy() -> dict[str, Any]:
    if not POLICY_PATH.is_file():
        raise FileNotFoundError(
            f"Policy file missing: {POLICY_PATH}"
        )

    with POLICY_PATH.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        policy = yaml.safe_load(handle)

    if not isinstance(policy, dict):
        raise RuntimeError(
            "Historical booster policy must be a YAML object."
        )

    return policy


def build_specialty_basis(
    policy: dict[str, Any],
) -> dict[str, str]:
    result: dict[str, str] = {}

    records = policy.get(
        "explicit_specialty_draft_products",
        [],
    )

    for record in records:
        if not isinstance(record, dict):
            continue

        canonical_id = clean_text(
            record.get(
                "canonical_product_id"
            )
        )

        specialty_basis = clean_text(
            record.get(
                "specialty_basis"
            )
        )

        if canonical_id:
            result[canonical_id] = (
                specialty_basis
            )

    return result


def compile_structural_pattern(
    policy: dict[str, Any],
) -> re.Pattern[str]:
    patterns = [
        clean_text(value)
        for value in policy.get(
            "structural_exclusion_name_patterns",
            [],
        )
        if clean_text(value)
    ]

    if not patterns:
        raise RuntimeError(
            "No structural-exclusion patterns configured."
        )

    escaped = [
        re.escape(value)
        for value in patterns
    ]

    return re.compile(
        "|".join(escaped),
        flags=re.IGNORECASE,
    )


def main() -> int:
    policy = load_policy()

    if not CANDIDATE_LANE_PATH.is_file():
        raise FileNotFoundError(
            "Candidate-lane input missing: "
            f"{CANDIDATE_LANE_PATH}"
        )

    candidates = pd.read_csv(
        CANDIDATE_LANE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(candidates) != 140:
        raise RuntimeError(
            "Expected 140 corrected historical candidates; "
            f"found {len(candidates)}."
        )

    if (
        candidates[
            "canonical_product_id"
        ].nunique()
        != 140
    ):
        raise RuntimeError(
            "Historical candidate IDs are not unique."
        )

    specialty_ids = {
        clean_text(value)
        for value in policy.get(
            "explicit_specialty_draft_product_ids",
            [],
        )
        if clean_text(value)
    }

    commander_review_ids = {
        clean_text(value)
        for value in policy.get(
            "commander_draft_policy_review_product_ids",
            [],
        )
        if clean_text(value)
    }

    if len(specialty_ids) != 7:
        raise RuntimeError(
            "Expected exactly 7 explicit specialty Draft IDs; "
            f"found {len(specialty_ids)}."
        )

    if len(commander_review_ids) != 2:
        raise RuntimeError(
            "Expected exactly 2 Commander Draft review IDs; "
            f"found {len(commander_review_ids)}."
        )

    overlap = (
        specialty_ids
        & commander_review_ids
    )

    if overlap:
        raise RuntimeError(
            "Specialty and Commander-review ID lists overlap: "
            + ", ".join(
                sorted(overlap)
            )
        )

    specialty_basis = (
        build_specialty_basis(
            policy
        )
    )

    structural_pattern = (
        compile_structural_pattern(
            policy
        )
    )

    output_rows: list[
        dict[str, Any]
    ] = []

    for _, row in candidates.iterrows():
        canonical_id = clean_text(
            row.get(
                "canonical_product_id"
            )
        )

        product_name = clean_text(
            row.get(
                "canonical_product_name"
            )
        )

        product_type = clean_text(
            row.get(
                "canonical_product_type"
            )
        )

        if structural_pattern.search(
            product_name
        ):
            raise RuntimeError(
                "Corrected historical input contains a "
                "structurally excluded product: "
                f"{canonical_id} | {product_name}"
            )

        if canonical_id in specialty_ids:
            if product_type != (
                "draft_booster_display"
            ):
                raise RuntimeError(
                    "Explicit specialty ID is not classified "
                    "as a Draft Booster display: "
                    f"{canonical_id}"
                )

            cohort = (
                "explicit_specialty_draft_review"
            )

            reason = (
                "explicit_product_policy_specialty_review"
            )

            basis = specialty_basis.get(
                canonical_id,
                "",
            )

        elif canonical_id in commander_review_ids:
            if product_type != (
                "draft_booster_display"
            ):
                raise RuntimeError(
                    "Commander review ID is not classified "
                    "as a Draft Booster display: "
                    f"{canonical_id}"
                )

            cohort = (
                "commander_draft_policy_review"
            )

            reason = (
                "commander_draft_requires_explicit_policy_decision"
            )

            basis = ""

        elif product_type == (
            "draft_booster_display"
        ):
            raise RuntimeError(
                "Corrected historical input contains an "
                "unapproved ordinary Draft display: "
                f"{canonical_id} | {product_name}"
            )

        else:
            cohort = (
                "traditional_historical_review"
            )

            reason = (
                "traditional_display_requires_historical_evidence_review"
            )

            basis = ""

        output_rows.append(
            {
                "canonical_product_id": (
                    canonical_id
                ),
                "tcgplayer_product_id": clean_text(
                    row.get(
                        "tcgplayer_product_id"
                    )
                ),
                "canonical_set_name": clean_text(
                    row.get(
                        "canonical_set_name"
                    )
                ),
                "canonical_product_name": (
                    product_name
                ),
                "canonical_product_type": (
                    product_type
                ),
                "canonical_packaging_level": clean_text(
                    row.get(
                        "canonical_packaging_level"
                    )
                ),
                "prior_candidate_review_lane": clean_text(
                    row.get(
                        "candidate_review_lane"
                    )
                ),
                "governed_candidate_cohort": (
                    cohort
                ),
                "cohort_reason": reason,
                "specialty_basis": basis,
                "price_review_state": clean_text(
                    row.get(
                        "price_review_state"
                    )
                ),
                "price_source_type": clean_text(
                    row.get(
                        "price_source_type"
                    )
                ),
                "market_price": clean_text(
                    row.get(
                        "market_price"
                    )
                ),
                "current_price_candidate": clean_text(
                    row.get(
                        "current_price_candidate"
                    )
                ),
                "release_timing_state": (
                    "external_release_timing_required"
                ),
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

    output = (
        pd.DataFrame(
            output_rows,
            columns=OUTPUT_COLUMNS,
        )
        .sort_values(
            [
                "governed_candidate_cohort",
                "canonical_product_name",
                "canonical_product_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    cohort_counts = {
        str(key): int(value)
        for key, value in (
            output[
                "governed_candidate_cohort"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    expected_counts = {
        "explicit_specialty_draft_review": 7,
        "commander_draft_policy_review": 2,
        "traditional_historical_review": 131,
    }

    if cohort_counts != expected_counts:
        raise RuntimeError(
            "Unexpected cohort counts. "
            f"Expected {expected_counts}; "
            f"found {cohort_counts}."
        )

    commander_names = set(
        output.loc[
            output[
                "governed_candidate_cohort"
            ].eq(
                "commander_draft_policy_review"
            ),
            "canonical_product_name",
        ].tolist()
    )

    expected_commander_names = {
        "Commander Legends - Draft Booster Box",
        (
            "Commander Legends: Battle for Baldur's Gate "
            "- Draft Booster Box"
        ),
    }

    if commander_names != expected_commander_names:
        raise RuntimeError(
            "Commander policy-review products do not match "
            "the expected explicit product set."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    cohort_path = (
        OUTPUT_ROOT
        / "historical_governed_candidate_cohorts_2026-07-22.csv"
    )

    specialty_path = (
        OUTPUT_ROOT
        / "historical_explicit_specialty_draft_review_2026-07-22.csv"
    )

    commander_path = (
        OUTPUT_ROOT
        / "historical_commander_draft_policy_review_2026-07-22.csv"
    )

    exclusions_path = (
        OUTPUT_ROOT
        / "historical_structural_and_ordinary_draft_exclusions_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_governed_candidate_cohort_summary_2026-07-22.json"
    )

    specialty = output[
        output[
            "governed_candidate_cohort"
        ].eq(
            "explicit_specialty_draft_review"
        )
    ].copy()

    commander = output[
        output[
            "governed_candidate_cohort"
        ].eq(
            "commander_draft_policy_review"
        )
    ].copy()

    exclusions = output.iloc[0:0].copy()

    output.to_csv(
        cohort_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    specialty.to_csv(
        specialty_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    commander.to_csv(
        commander_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    exclusions.to_csv(
        exclusions_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "resolution_status": "PASS",
        "historical_candidate_rows": int(
            len(output)
        ),
        "unique_canonical_product_ids": int(
            output[
                "canonical_product_id"
            ].nunique()
        ),
        "cohort_counts": cohort_counts,
        "products_removed_from_premium_candidate_population": int(
            len(exclusions)
        ),
        "products_remaining_in_historical_review": int(
            output[
                "governed_candidate_cohort"
            ].isin(
                [
                    "explicit_specialty_draft_review",
                    "commander_draft_policy_review",
                    "traditional_historical_review",
                ]
            ).sum()
        ),
        "release_timing_resolved_rows": 0,
        "final_eligibility_assigned": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "all_cohorts": str(
                cohort_path
            ),
            "explicit_specialty_review": str(
                specialty_path
            ),
            "commander_policy_review": str(
                commander_path
            ),
            "exclusions": str(
                exclusions_path
            ),
        },
    }

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.1D.2.3C "
        "Explicit Historical Booster Cohort Policy"
    )
    print("=" * 76)
    print(
        f"Historical candidate rows: {len(output)}"
    )

    for cohort_name in sorted(
        cohort_counts
    ):
        print(
            f"{cohort_name}: "
            f"{cohort_counts[cohort_name]}"
        )

    print()
    print(
        "Products removed from premium candidate population: "
        f"{len(exclusions)}"
    )
    print(
        "Products remaining in historical review: "
        + str(
            summary[
                "products_remaining_in_historical_review"
            ]
        )
    )
    print()
    print(
        "COHORT POLICY RESOLUTION: PASS"
    )
    print(
        "Release timing: UNRESOLVED"
    )
    print(
        "Final eligibility: NOT ASSIGNED"
    )
    print(
        "Scoring: DISABLED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal database: UNCHANGED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())