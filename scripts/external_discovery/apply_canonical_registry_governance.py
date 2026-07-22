from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CANONICAL_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry"
    / "canonical_mtg_product_registry_2026-07-22.csv"
)

DEFAULT_POLICY_PATH = (
    ROOT
    / "config"
    / "canonical_registry_governance.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "canonical_registry_governance"
)

GOVERNANCE_VERSION = "10.5R.1C.2.1"

GOVERNANCE_COLUMNS = [
    "canonical_product_id",
    "canonical_registry_version",
    "governance_version",
    "governance_effective_at_utc",
    "identity_lifecycle_status",
    "source_availability_status",
    "governance_review_status",
    "governance_review_reason",
    "superseded_by_canonical_product_id",
    "merged_into_canonical_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_class",
    "canonical_product_family",
    "canonical_product_type",
    "canonical_packaging_level",
    "language",
    "foil_variant",
    "edition_variant",
    "tcgplayer_product_id",
    "candidate_record_id",
    "registry_relationship",
    "reconciliation_status",
    "type_alignment",
    "investment_eligibility_status",
    "investment_approval_status",
    "scoring_status",
    "universal_export_status",
    "universal_export_block_reason",
    "existing_investment_product_id",
    "existing_approval_status",
    "existing_approval_method",
    "source_lineage",
]


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


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
            "Governance policy must be a mapping."
        )

    return policy


def require_policy_states(
    policy: dict[str, Any],
) -> None:
    required = {
        "identity_lifecycle_states",
        "source_availability_states",
        "governance_review_states",
        "investment_eligibility_states",
        "investment_approval_states",
        "scoring_states",
        "universal_export_states",
        "default_rules",
        "new_identity_rules",
        "universal_export_rules",
        "supersession_rules",
        "universal_mapping",
    }

    missing = sorted(
        required - set(policy)
    )

    if missing:
        raise ValueError(
            "Governance policy missing sections: "
            + ", ".join(missing)
        )


def determine_governance_review(
    canonical_identity_status: str,
) -> tuple[str, str]:
    if canonical_identity_status == (
        "new_source_identity"
    ):
        return (
            "required",
            "new_source_identity",
        )

    if canonical_identity_status == (
        "established_existing_identity"
    ):
        return (
            "not_required",
            "",
        )

    return (
        "required",
        "identity_status_requires_review",
    )


def determine_export_status(
    *,
    identity_lifecycle_status: str,
    source_availability_status: str,
    governance_review_status: str,
    eligibility_status: str,
    approval_status: str,
    scoring_status: str,
) -> tuple[str, str]:
    blocking_reasons: list[str] = []

    if identity_lifecycle_status in {
        "retired",
        "superseded",
        "identity_review_required",
    }:
        blocking_reasons.append(
            "identity_lifecycle_block"
        )

    if source_availability_status == (
        "unavailable"
    ):
        blocking_reasons.append(
            "source_unavailable"
        )

    if governance_review_status == (
        "rejected"
    ):
        blocking_reasons.append(
            "governance_rejected"
        )

    if blocking_reasons:
        return (
            "blocked",
            "|".join(blocking_reasons),
        )

    if (
        approval_status == "approved"
        and eligibility_status == "eligible"
        and scoring_status == "scored"
    ):
        return (
            "recommendation_ready",
            "",
        )

    if (
        eligibility_status == "eligible"
        and scoring_status == "scored"
    ):
        return (
            "analytics_ready",
            "",
        )

    return (
        "identity_ready",
        "",
    )


def build_governed_registry(
    canonical: pd.DataFrame,
) -> pd.DataFrame:
    generated_at = utc_now()
    output_rows: list[dict[str, Any]] = []

    for _, row in canonical.iterrows():
        canonical_identity_status = clean_text(
            row.get(
                "canonical_identity_status"
            )
        )

        (
            governance_review_status,
            governance_review_reason,
        ) = determine_governance_review(
            canonical_identity_status
        )

        identity_lifecycle_status = "active"
        source_availability_status = "available"

        eligibility_status = (
            clean_text(
                row.get(
                    "investment_eligibility_status"
                )
            )
            or "not_evaluated"
        )

        approval_status = (
            clean_text(
                row.get(
                    "investment_approval_status"
                )
            )
            or "review_required"
        )

        scoring_status = (
            clean_text(
                row.get(
                    "scoring_status"
                )
            )
            or "not_scored"
        )

        (
            universal_export_status,
            universal_export_block_reason,
        ) = determine_export_status(
            identity_lifecycle_status=(
                identity_lifecycle_status
            ),
            source_availability_status=(
                source_availability_status
            ),
            governance_review_status=(
                governance_review_status
            ),
            eligibility_status=(
                eligibility_status
            ),
            approval_status=(
                approval_status
            ),
            scoring_status=scoring_status,
        )

        output_rows.append(
            {
                "canonical_product_id": (
                    clean_text(
                        row.get(
                            "canonical_product_id"
                        )
                    )
                ),
                "canonical_registry_version": (
                    clean_text(
                        row.get(
                            "canonical_registry_version"
                        )
                    )
                ),
                "governance_version": (
                    GOVERNANCE_VERSION
                ),
                "governance_effective_at_utc": (
                    generated_at
                ),
                "identity_lifecycle_status": (
                    identity_lifecycle_status
                ),
                "source_availability_status": (
                    source_availability_status
                ),
                "governance_review_status": (
                    governance_review_status
                ),
                "governance_review_reason": (
                    governance_review_reason
                ),
                "superseded_by_canonical_product_id": "",
                "merged_into_canonical_product_id": "",
                "canonical_set_name": (
                    clean_text(
                        row.get(
                            "canonical_set_name"
                        )
                    )
                ),
                "canonical_product_name": (
                    clean_text(
                        row.get(
                            "canonical_product_name"
                        )
                    )
                ),
                "canonical_product_class": (
                    clean_text(
                        row.get(
                            "canonical_product_class"
                        )
                    )
                ),
                "canonical_product_family": (
                    clean_text(
                        row.get(
                            "canonical_product_family"
                        )
                    )
                ),
                "canonical_product_type": (
                    clean_text(
                        row.get(
                            "canonical_product_type"
                        )
                    )
                ),
                "canonical_packaging_level": (
                    clean_text(
                        row.get(
                            "canonical_packaging_level"
                        )
                    )
                ),
                "language": clean_text(
                    row.get("language")
                ),
                "foil_variant": clean_text(
                    row.get("foil_variant")
                ),
                "edition_variant": clean_text(
                    row.get("edition_variant")
                ),
                "tcgplayer_product_id": (
                    clean_text(
                        row.get(
                            "tcgplayer_product_id"
                        )
                    )
                ),
                "candidate_record_id": (
                    clean_text(
                        row.get(
                            "candidate_record_id"
                        )
                    )
                ),
                "registry_relationship": (
                    clean_text(
                        row.get(
                            "registry_relationship"
                        )
                    )
                ),
                "reconciliation_status": (
                    clean_text(
                        row.get(
                            "reconciliation_status"
                        )
                    )
                ),
                "type_alignment": clean_text(
                    row.get(
                        "type_alignment"
                    )
                ),
                "investment_eligibility_status": (
                    eligibility_status
                ),
                "investment_approval_status": (
                    approval_status
                ),
                "scoring_status": (
                    scoring_status
                ),
                "universal_export_status": (
                    universal_export_status
                ),
                "universal_export_block_reason": (
                    universal_export_block_reason
                ),
                "existing_investment_product_id": (
                    clean_text(
                        row.get(
                            "existing_investment_product_id"
                        )
                    )
                ),
                "existing_approval_status": (
                    clean_text(
                        row.get(
                            "existing_approval_status"
                        )
                    )
                ),
                "existing_approval_method": (
                    clean_text(
                        row.get(
                            "existing_approval_method"
                        )
                    )
                ),
                "source_lineage": (
                    clean_text(
                        row.get(
                            "source_lineage"
                        )
                    )
                ),
            }
        )

    governed = pd.DataFrame(
        output_rows,
        columns=GOVERNANCE_COLUMNS,
    )

    return governed.sort_values(
        [
            "canonical_product_class",
            "canonical_product_family",
            "canonical_product_type",
            "canonical_set_name",
            "canonical_product_name",
            "canonical_product_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def write_outputs(
    governed: pd.DataFrame,
    canonical_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    governed_path = (
        OUTPUT_ROOT
        / "governed_canonical_mtg_registry_2026-07-22.csv"
    )

    review_path = (
        VALIDATION_ROOT
        / "canonical_governance_review_queue_2026-07-22.csv"
    )


    summary_path = (
        VALIDATION_ROOT
        / "canonical_governance_summary_2026-07-22.json"
    )

    governed.to_csv(
        governed_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    review_queue = governed[
        governed[
            "governance_review_status"
        ].eq("required")
    ].copy()

    identity_ready = governed[
        governed[
            "universal_export_status"
        ].isin(
            [
                "identity_ready",
                "analytics_ready",
                "recommendation_ready",
            ]
        )
    ].copy()

    review_queue.to_csv(
        review_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


    def counts(
        column: str,
    ) -> dict[str, int]:
        return {
            str(key): int(value)
            for key, value in (
                governed[column]
                .value_counts(
                    dropna=False
                )
                .to_dict()
                .items()
            )
        }

    summary = {
        "schema_version": (
            GOVERNANCE_VERSION
        ),
        "generated_at_utc": utc_now(),
        "governance_status": (
            "GOVERNANCE_MODEL_APPLIED"
        ),
        "governed_registry_rows": int(
            len(governed)
        ),
        "unique_canonical_product_ids": int(
            governed[
                "canonical_product_id"
            ].nunique()
        ),
        "identity_lifecycle_status_counts": (
            counts(
                "identity_lifecycle_status"
            )
        ),
        "source_availability_status_counts": (
            counts(
                "source_availability_status"
            )
        ),
        "governance_review_status_counts": (
            counts(
                "governance_review_status"
            )
        ),
        "investment_eligibility_status_counts": (
            counts(
                "investment_eligibility_status"
            )
        ),
        "investment_approval_status_counts": (
            counts(
                "investment_approval_status"
            )
        ),
        "scoring_status_counts": (
            counts(
                "scoring_status"
            )
        ),
        "universal_export_status_counts": (
            counts(
                "universal_export_status"
            )
        ),
        "governance_review_rows": int(
            len(review_queue)
        ),
        "universal_identity_ready_rows": int(
            len(identity_ready)
        ),
        "input_files": {
            "canonical_registry": str(
                canonical_path
            ),
            "governance_policy": str(
                policy_path
            ),
        },
        "output_files": {
            "governed_registry": str(
                governed_path
            ),
            "governance_review_queue": str(
                review_path
            ),

        },
        "canonical_registry_changed": False,
        "production_registry_changed": False,
        "database_changed": False,
        "eligibility_recalculated": False,
        "scoring_applied": False,
        "recommendations_created": False,
        "universal_package_created": False,
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
        "Phase 10.5R.1C.2.1 "
        "Canonical Registry Governance"
    )
    print("=" * 76)
    print(
        f"Governed registry rows: "
        f"{len(governed)}"
    )
    print(
        "Unique canonical product IDs: "
        f"{governed['canonical_product_id'].nunique()}"
    )
    print(
        f"Governance review rows: "
        f"{len(review_queue)}"
    )
    print(
        "Universal identity-ready rows: "
        f"{len(identity_ready)}"
    )
    print()
    print("Governance review states:")

    for name, count in sorted(
        summary[
            "governance_review_status_counts"
        ].items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"  {name}: {count}"
        )

    print()
    print("Universal export states:")

    for name, count in sorted(
        summary[
            "universal_export_status_counts"
        ].items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"  {name}: {count}"
        )

    print()
    print(
        "PHASE 10.5R.1C.2.1 "
        "GOVERNANCE MODEL: PASS"
    )
    print(
        "Canonical registry: UNCHANGED"
    )
    print(
        "Production registry: UNCHANGED"
    )
    print(
        "Universal package: NOT CREATED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--canonical-registry",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
    )

    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    canonical_path = (
        args.canonical_registry.resolve()
    )

    policy_path = (
        args.policy.resolve()
    )

    if not canonical_path.is_file():
        raise FileNotFoundError(
            "Canonical registry not found: "
            f"{canonical_path}"
        )

    if not policy_path.is_file():
        raise FileNotFoundError(
            "Governance policy not found: "
            f"{policy_path}"
        )

    policy = load_policy(
        policy_path
    )

    require_policy_states(
        policy
    )

    canonical = pd.read_csv(
        canonical_path,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    if len(canonical) != 5239:
        raise RuntimeError(
            "Expected 5,239 canonical rows; "
            f"found {len(canonical)}."
        )

    governed = build_governed_registry(
        canonical
    )

    if len(governed) != len(canonical):
        raise RuntimeError(
            "Governed registry row count "
            "does not match canonical registry."
        )

    if governed[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Governed registry contains "
            "duplicate canonical IDs."
        )

    write_outputs(
        governed,
        canonical_path,
        policy_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())