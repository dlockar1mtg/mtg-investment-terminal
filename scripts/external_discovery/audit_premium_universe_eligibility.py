from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GOVERNED_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
    / "governed_canonical_mtg_registry_2026-07-22.csv"
)

DEFAULT_POLICY_PATH = (
    ROOT
    / "config"
    / "premium_mtg_eligibility.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
)

ELIGIBILITY_VERSION = "10.5R.1D.1.1"

AUDIT_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_class",
    "canonical_product_family",
    "canonical_product_type",
    "canonical_packaging_level",
    "identity_lifecycle_status",
    "source_availability_status",
    "governance_review_status",
    "investment_approval_status",
    "prior_investment_eligibility_status",
    "structural_eligibility_state",
    "structural_eligibility_reason",
    "final_eligibility_decision",
    "final_decision_reason",
    "historical_review_required",
    "sealed_product_review_required",
    "classification_review_required",
    "scoring_allowed",
    "universal_investable_allowed",
]


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat().replace(
        "+00:00",
        "Z",
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


def normalize_identity_name(
    value: object,
) -> str:
    text = clean_text(value).casefold()

    for character in (
        ":",
        "-",
        "'",
        "’",
        "(",
        ")",
        "[",
        "]",
        "/",
        "&",
    ):
        text = text.replace(
            character,
            " ",
        )

    return " ".join(
        text.split()
    )


SPECIALTY_DRAFT_REVIEW_SETS = {
    normalize_identity_name(
        "Commander Masters"
    ),
    normalize_identity_name(
        "Dominaria Remastered"
    ),
    normalize_identity_name(
        "Double Masters 2022"
    ),
    normalize_identity_name(
        "Innistrad: Double Feature"
    ),
    normalize_identity_name(
        "Modern Horizons 2"
    ),
    normalize_identity_name(
        "Ravnica Remastered"
    ),
    normalize_identity_name(
        "Time Spiral: Remastered"
    ),
}


COMMANDER_DRAFT_REVIEW_SETS = {
    normalize_identity_name(
        "Commander Legends"
    ),
    normalize_identity_name(
        "Commander Legends: "
        "Battle for Baldur's Gate"
    ),
}


NON_BOOSTER_DISPLAY_MARKERS = (
    "planeswalker deck display",
    "booster battle pack",
    "basic booster display",
    "beyond booster",
    "epilogue booster",
)


def load_policy(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        policy = yaml.safe_load(handle)

    if not isinstance(policy, dict):
        raise ValueError(
            "Eligibility policy must be a mapping."
        )

    return policy


def governance_block_reason(
    row: pd.Series,
) -> str:
    reasons: list[str] = []

    if clean_text(
        row.get(
            "identity_lifecycle_status"
        )
    ) != "active":
        reasons.append(
            "identity_not_active"
        )

    if clean_text(
        row.get(
            "source_availability_status"
        )
    ) != "available":
        reasons.append(
            "source_not_available"
        )

    if clean_text(
        row.get(
            "governance_review_status"
        )
    ) == "rejected":
        reasons.append(
            "governance_rejected"
        )

    if clean_text(
        row.get(
            "universal_export_status"
        )
    ) == "blocked":
        reasons.append(
            "universal_export_blocked"
        )

    if not clean_text(
        row.get(
            "canonical_product_id"
        )
    ):
        reasons.append(
            "blank_canonical_product_id"
        )

    if not clean_text(
        row.get(
            "tcgplayer_product_id"
        )
    ):
        reasons.append(
            "blank_tcgplayer_product_id"
        )

    return "|".join(reasons)


def classify_secret_lair(
    *,
    product_type: str,
    packaging_level: str,
    product_name: str,
) -> tuple[str, str]:
    normalized_name = product_name.casefold()

    if packaging_level == "case":
        return (
            "structurally_ineligible",
            "case_level_product_excluded",
        )

    if (
        product_type == "secret_lair_insert"
        or packaging_level
        == "individual_card_insert"
    ):
        return (
            "structurally_ineligible",
            "secret_lair_insert_excluded",
        )

    if (
        product_type
        == "secret_lair_card_variant"
    ):
        return (
            "structurally_ineligible",
            "separately_listed_secret_lair_card_variant",
        )

    if packaging_level == (
        "individual_card_or_variant"
    ):
        return (
            "structurally_ineligible",
            "individual_card_from_secret_lair_drop",
        )

    if packaging_level == "deck":
        return (
            "structurally_ineligible",
            "secret_lair_commander_deck_excluded",
        )

    if (
        product_type
        == "secret_lair_card_or_product"
        and "commander deck"
        in normalized_name
    ):
        return (
            "structurally_ineligible",
            "secret_lair_commander_deck_excluded",
        )

    if (
        product_type
        == "secret_lair_bundle_or_kit"
    ):
        return (
            "structurally_eligible",
            "sealed_secret_lair_bundle_or_kit",
        )

    if (
        product_type
        == "secret_lair_card_or_product"
    ):
        return (
            "sealed_product_review_required",
            "sealed_status_not_proven_by_current_classification",
        )

    if "display case" in normalized_name:
        return (
            "structurally_ineligible",
            "case_level_product_excluded",
        )

    return (
        "sealed_product_review_required",
        "secret_lair_sealed_status_requires_verification",
    )


def classify_sealed(
    *,
    product_type: str,
    packaging_level: str,
    product_name: str,
    set_name: str,
) -> tuple[str, str]:
    normalized_name = normalize_identity_name(
        product_name
    )

    normalized_set_name = normalize_identity_name(
        set_name
    )

    if (
        packaging_level == "case"
        or "display case" in normalized_name
        or normalized_name.endswith(" case")
    ):
        return (
            "structurally_ineligible",
            "case_level_product_excluded",
        )

    if product_type in {
        "commander_deck",
        "bundle",
        "play_booster_display",
        "set_booster_display",
        "theme_booster_display",
        "jumpstart_booster_display",
    }:
        return (
            "structurally_ineligible",
            f"excluded_product_type:{product_type}",
        )

    if packaging_level in {
        "individual_card_or_variant",
        "individual_card_insert",
    }:
        return (
            "structurally_ineligible",
            f"excluded_packaging:{packaging_level}",
        )

    if any(
        marker in normalized_name
        for marker in NON_BOOSTER_DISPLAY_MARKERS
    ):
        return (
            "structurally_ineligible",
            "non_booster_display_product_excluded",
        )

    if (
        product_type
        == "collector_booster_display"
    ):
        return (
            "structurally_eligible",
            "collector_booster_display",
        )

    if (
        product_type
        == "traditional_booster_display"
    ):
        return (
            "historical_review_required",
            (
                "traditional_booster_display"
                "_requires_premium_history_review"
            ),
        )

    if product_type == "draft_booster_display":
        if (
            normalized_set_name
            in SPECIALTY_DRAFT_REVIEW_SETS
        ):
            return (
                "historical_review_required",
                (
                    "specialty_draft_booster_display"
                    "_requires_premium_history_review"
                ),
            )

        if (
            normalized_set_name
            in COMMANDER_DRAFT_REVIEW_SETS
        ):
            return (
                "historical_review_required",
                (
                    "commander_draft_booster_display"
                    "_requires_policy_review"
                ),
            )

        return (
            "structurally_ineligible",
            "ordinary_draft_booster_display_excluded",
        )

    if product_type == "sealed_case":
        return (
            "structurally_ineligible",
            "case_level_product_excluded",
        )

    return (
        "classification_review_required",
        "sealed_product_type_not_covered",
    )


def classify_row(
    row: pd.Series,
) -> tuple[str, str]:
    blocked_reason = governance_block_reason(
        row
    )

    if blocked_reason:
        return (
            "structurally_ineligible",
            f"governance_block:{blocked_reason}",
        )

    product_class = clean_text(
        row.get(
            "canonical_product_class"
        )
    )

    product_type = clean_text(
        row.get(
            "canonical_product_type"
        )
    )

    packaging_level = clean_text(
        row.get(
            "canonical_packaging_level"
        )
    )

    product_name = clean_text(
        row.get(
            "canonical_product_name"
        )
    )

    set_name = clean_text(
        row.get(
            "canonical_set_name"
        )
    )

    if product_class == (
        "secret_lair_product"
    ):
        return classify_secret_lair(
            product_type=product_type,
            packaging_level=packaging_level,
            product_name=product_name,
        )

    if product_class == "sealed_product":
        return classify_sealed(
            product_type=product_type,
            packaging_level=packaging_level,
            product_name=product_name,
            set_name=set_name,
        )

    return (
        "classification_review_required",
        "unsupported_canonical_product_class",
    )


def build_audit(
    governed: pd.DataFrame,
) -> pd.DataFrame:
    output_rows: list[
        dict[str, Any]
    ] = []

    for _, row in governed.iterrows():
        (
            structural_state,
            structural_reason,
        ) = classify_row(row)

        output_rows.append(
            {
                "canonical_product_id": clean_text(
                    row.get(
                        "canonical_product_id"
                    )
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
                "canonical_product_name": clean_text(
                    row.get(
                        "canonical_product_name"
                    )
                ),
                "canonical_product_class": clean_text(
                    row.get(
                        "canonical_product_class"
                    )
                ),
                "canonical_product_family": clean_text(
                    row.get(
                        "canonical_product_family"
                    )
                ),
                "canonical_product_type": clean_text(
                    row.get(
                        "canonical_product_type"
                    )
                ),
                "canonical_packaging_level": clean_text(
                    row.get(
                        "canonical_packaging_level"
                    )
                ),
                "identity_lifecycle_status": clean_text(
                    row.get(
                        "identity_lifecycle_status"
                    )
                ),
                "source_availability_status": clean_text(
                    row.get(
                        "source_availability_status"
                    )
                ),
                "governance_review_status": clean_text(
                    row.get(
                        "governance_review_status"
                    )
                ),
                "investment_approval_status": clean_text(
                    row.get(
                        "investment_approval_status"
                    )
                ),
                "prior_investment_eligibility_status": (
                    clean_text(
                        row.get(
                            "investment_eligibility_status"
                        )
                    )
                ),
                "structural_eligibility_state": (
                    structural_state
                ),
                "structural_eligibility_reason": (
                    structural_reason
                ),
                "final_eligibility_decision": (
                    "not_decided"
                ),
                "final_decision_reason": "",
                "historical_review_required": (
                    structural_state
                    == "historical_review_required"
                ),
                "sealed_product_review_required": (
                    structural_state
                    == "sealed_product_review_required"
                ),
                "classification_review_required": (
                    structural_state
                    == "classification_review_required"
                ),
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

    return pd.DataFrame(
        output_rows,
        columns=AUDIT_COLUMNS,
    ).sort_values(
        [
            "structural_eligibility_state",
            "canonical_product_class",
            "canonical_product_type",
            "canonical_product_name",
            "canonical_product_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def write_csv(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


def write_outputs(
    *,
    audit: pd.DataFrame,
    governed_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "premium_universe_eligibility_audit_2026-07-22.csv"
    )

    review_path = (
        OUTPUT_ROOT
        / "premium_universe_eligibility_review_queue_2026-07-22.csv"
    )

    candidate_path = (
        OUTPUT_ROOT
        / "premium_universe_structural_candidates_2026-07-22.csv"
    )

    exclusion_path = (
        OUTPUT_ROOT
        / "premium_universe_structural_exclusions_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "premium_universe_eligibility_summary_2026-07-22.json"
    )

    secret_lair_candidate_path = (
        OUTPUT_ROOT
        / "secret_lair_structural_candidates_2026-07-22.csv"
    )

    historical_review_path = (
        OUTPUT_ROOT
        / "historical_booster_review_2026-07-22.csv"
    )

    classification_review_path = (
        OUTPUT_ROOT
        / "sealed_product_classification_review_2026-07-22.csv"
    )

    review_states = {
        "historical_review_required",
        "sealed_product_review_required",
        "classification_review_required",
    }

    review = audit[
        audit[
            "structural_eligibility_state"
        ].isin(review_states)
    ].copy()

    candidates = audit[
        audit[
            "structural_eligibility_state"
        ].eq("structurally_eligible")
    ].copy()

    exclusions = audit[
        audit[
            "structural_eligibility_state"
        ].eq("structurally_ineligible")
    ].copy()

    secret_lair_candidates = audit[
        audit[
            "canonical_product_class"
        ].eq("secret_lair_product")
        & audit[
            "structural_eligibility_state"
        ].eq("structurally_eligible")
    ].copy()

    historical_review = audit[
        audit[
            "structural_eligibility_state"
        ].eq("historical_review_required")
    ].copy()

    classification_review = audit[
        audit[
            "structural_eligibility_state"
        ].eq("classification_review_required")
    ].copy()

    write_csv(
        audit,
        audit_path,
    )

    write_csv(
        review,
        review_path,
    )

    write_csv(
        candidates,
        candidate_path,
    )

    write_csv(
        exclusions,
        exclusion_path,
    )

    write_csv(
        secret_lair_candidates,
        secret_lair_candidate_path,
    )

    write_csv(
        historical_review,
        historical_review_path,
    )

    write_csv(
        classification_review,
        classification_review_path,
    )

    state_counts = {
        str(key): int(value)
        for key, value in (
            audit[
                "structural_eligibility_state"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    reason_counts = {
        str(key): int(value)
        for key, value in (
            audit[
                "structural_eligibility_reason"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": (
            ELIGIBILITY_VERSION
        ),
        "generated_at_utc": utc_now(),
        "audit_status": "PASS",
        "audit_rows": int(
            len(audit)
        ),
        "unique_canonical_product_ids": int(
            audit[
                "canonical_product_id"
            ].nunique()
        ),
        "structural_eligibility_state_counts": (
            state_counts
        ),
        "structural_eligibility_reason_counts": (
            reason_counts
        ),
        "structural_candidate_rows": int(
            len(candidates)
        ),
        "structural_exclusion_rows": int(
            len(exclusions)
        ),
        "review_queue_rows": int(
            len(review)
        ),
        "secret_lair_candidate_rows": int(
            len(secret_lair_candidates)
        ),
        "historical_review_rows": int(
            len(historical_review)
        ),
        "classification_review_rows": int(
            len(classification_review)
        ),
        "final_eligible_rows": 0,
        "final_ineligible_rows": 0,
        "not_decided_rows": int(
            len(audit)
        ),
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "input_files": {
            "governed_registry": str(
                governed_path
            ),
            "eligibility_policy": str(
                policy_path
            ),
        },
        "output_files": {
            "eligibility_audit": str(
                audit_path
            ),
            "review_queue": str(
                review_path
            ),
            "structural_candidates": str(
                candidate_path
            ),
            "structural_exclusions": str(
                exclusion_path
            ),
            "secret_lair_candidates": str(
                secret_lair_candidate_path
            ),
            "historical_review": str(
                historical_review_path
            ),
            "classification_review": str(
                classification_review_path
            ),
        },
        "canonical_registry_changed": False,
        "governed_registry_changed": False,
        "production_registry_changed": False,
        "eligibility_promoted": False,
        "scoring_applied": False,
        "recommendations_created": False,
        "universal_package_created": False,
        "universal_database_changed": False,
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
        "Phase 10.5R.1D.1 "
        "Premium Universe Eligibility Audit"
    )
    print("=" * 76)
    print(
        f"Audit rows: {len(audit)}"
    )
    print(
        "Unique canonical IDs: "
        f"{audit['canonical_product_id'].nunique()}"
    )
    print()

    for name, count in sorted(
        state_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{name}: {count}"
        )

    print()
    print(
        f"Structural candidates: "
        f"{len(candidates)}"
    )
    print(
        f"Structural exclusions: "
        f"{len(exclusions)}"
    )
    print(
        f"Review queue: {len(review)}"
    )
    print(
        "Final eligible decisions: 0"
    )
    print(
        "Scoring allowed: 0"
    )
    print(
        "Universal investable allowed: 0"
    )
    print()
    print(
        "PHASE 10.5R.1D.1 "
        "ELIGIBILITY AUDIT: PASS"
    )
    print(
        "Eligibility promotion: NOT APPLIED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal database: UNCHANGED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--governed-registry",
        type=Path,
        default=DEFAULT_GOVERNED_PATH,
    )

    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    governed_path = (
        args.governed_registry.resolve()
    )

    policy_path = (
        args.policy.resolve()
    )

    if not governed_path.is_file():
        raise FileNotFoundError(
            "Governed registry not found: "
            f"{governed_path}"
        )

    if not policy_path.is_file():
        raise FileNotFoundError(
            "Eligibility policy not found: "
            f"{policy_path}"
        )

    policy = load_policy(
        policy_path
    )

    if (
        policy.get("schema_version")
        != ELIGIBILITY_VERSION
    ):
        raise RuntimeError(
            "Eligibility policy version mismatch."
        )

    governed = pd.read_csv(
        governed_path,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    if len(governed) != 5239:
        raise RuntimeError(
            "Expected 5,239 governed identities; "
            f"found {len(governed)}."
        )

    audit = build_audit(
        governed
    )

    if len(audit) != len(governed):
        raise RuntimeError(
            "Eligibility audit row count mismatch."
        )

    if audit[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Eligibility audit contains "
            "duplicate canonical IDs."
        )

    write_outputs(
        audit=audit,
        governed_path=governed_path,
        policy_path=policy_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())