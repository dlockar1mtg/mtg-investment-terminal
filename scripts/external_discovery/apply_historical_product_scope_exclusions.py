from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

SEALED_AUDIT_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_mtgjson_sealed_products"
    / "historical_mtgjson_sealed_product_audit_2026-07-22.csv"
)

RELEASE_ADJUDICATION_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_release_adjudication"
    / "historical_release_evidence_adjudication_2026-07-22.csv"
)

FINAL_RELEASE_DATE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_final_release_dates"
    / "historical_final_governed_release_dates_2026-07-22.csv"
)

SCOPE_POLICY_PATH = (
    ROOT
    / "config"
    / "historical_product_scope_exclusions.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_product_scope"
)

SCHEMA_VERSION = "10.5R.1D.2.4E.3"

EXCLUSION_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "scope_state",
    "scope_exclusion_reason",
    "scope_exclusion_basis",
    "general_foreign_language_filter_created",
    "selected_sealed_name",
    "selected_sealed_tcgplayer_product_id",
    "sealed_match_method",
    "sealed_match_state",
    "set_release_date",
    "tcgcsv_release_date_candidate",
    "product_release_date_candidate",
    "governed_release_date",
    "governed_release_date_source",
    "governed_release_date_state",
    "release_date_governance_reason",
    "official_exception_applied",
    "final_release_date_assigned",
    "historical_eligibility_decision",
    "scoring_allowed",
    "universal_investable_allowed",
]

ACTIVE_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "canonical_set_name",
    "governed_candidate_cohort",
    "scope_state",
    "scope_exclusion_reason",
    "scope_exclusion_basis",
    "selected_set_code",
    "selected_set_name",
    "selected_sealed_uuid",
    "selected_sealed_name",
    "selected_sealed_category",
    "selected_sealed_subtype",
    "selected_sealed_release_date",
    "selected_sealed_tcgplayer_product_id",
    "sealed_match_method",
    "sealed_match_score",
    "sealed_match_state",
    "set_release_date",
    "tcgcsv_release_date_candidate",
    "product_release_date_candidate",
    "release_evidence_state",
    "governed_release_date",
    "governed_release_date_source",
    "governed_release_date_state",
    "release_date_governance_reason",
    "official_exception_applied",
    "final_release_date_assigned",
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


def repository_relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_policy() -> dict[str, Any]:
    with SCOPE_POLICY_PATH.open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        policy = yaml.safe_load(handle)

    if not isinstance(policy, dict):
        raise RuntimeError(
            "Historical scope policy must be a YAML object."
        )

    return policy


def build_exclusion_index(
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    exclusions: dict[str, dict[str, Any]] = {}

    for record in policy.get(
        "excluded_products",
        [],
    ):
        if not isinstance(record, dict):
            continue

        canonical_id = clean_text(
            record.get("canonical_product_id")
        )

        if not canonical_id:
            continue

        if canonical_id in exclusions:
            raise RuntimeError(
                "Duplicate scope exclusion: "
                f"{canonical_id}"
            )

        exclusions[canonical_id] = record

    return exclusions


def main() -> int:
    for required_path in (
        SEALED_AUDIT_PATH,
        RELEASE_ADJUDICATION_PATH,
        FINAL_RELEASE_DATE_PATH,
        SCOPE_POLICY_PATH,
    ):
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Required input missing: {required_path}"
            )

    sealed_audit = pd.read_csv(
        SEALED_AUDIT_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    adjudication = pd.read_csv(
        RELEASE_ADJUDICATION_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    final_release_dates = pd.read_csv(
        FINAL_RELEASE_DATE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if len(sealed_audit) != 140:
        raise RuntimeError(
            "Expected 140 sealed-product rows; "
            f"found {len(sealed_audit)}."
        )

    if len(adjudication) != 140:
        raise RuntimeError(
            "Expected 140 release-adjudication rows; "
            f"found {len(adjudication)}."
        )

    if len(final_release_dates) != 140:
        raise RuntimeError(
            "Expected 140 final release-date rows; "
            f"found {len(final_release_dates)}."
        )

    final_ids = set(
        final_release_dates["canonical_product_id"]
    )

    sealed_ids = set(
        sealed_audit["canonical_product_id"]
    )

    adjudication_ids = set(
        adjudication["canonical_product_id"]
    )

    if len(final_ids) != 140:
        raise RuntimeError(
            "Final release-date input does not contain "
            "140 unique canonical IDs."
        )

    if final_ids != sealed_ids:
        raise RuntimeError(
            "Final release-date and sealed-product identities differ."
        )

    if final_ids != adjudication_ids:
        raise RuntimeError(
            "Final release-date and adjudication identities differ."
        )

    final_release_index = (
        final_release_dates
        .set_index("canonical_product_id")
        .to_dict(orient="index")
    )

    policy = load_policy()
    exclusions = build_exclusion_index(policy)

    if len(exclusions) != 1:
        raise RuntimeError(
            "Expected exactly one product-specific exclusion; "
            f"found {len(exclusions)}."
        )

    exclusion_id = next(iter(exclusions))
    exclusion_policy = exclusions[exclusion_id]

    expected_id = "MTG-CANON-TCGPLAYER-245972"

    if exclusion_id != expected_id:
        raise RuntimeError(
            "Unexpected excluded product ID: "
            f"{exclusion_id}"
        )

    matching_rows = sealed_audit[
        sealed_audit[
            "canonical_product_id"
        ].eq(exclusion_id)
    ]

    if len(matching_rows) != 1:
        raise RuntimeError(
            "Excluded product must exist exactly once "
            "in the sealed-product audit."
        )

    excluded_rows: list[dict[str, Any]] = []
    active_rows: list[dict[str, Any]] = []

    for _, row in sealed_audit.iterrows():
        canonical_id = clean_text(
            row.get("canonical_product_id")
        )

        final_release_row = final_release_index[canonical_id]

        if canonical_id in exclusions:
            exclusion = exclusions[canonical_id]

            excluded_rows.append(
                {
                    "canonical_product_id": canonical_id,
                    "tcgplayer_product_id": clean_text(
                        row.get("tcgplayer_product_id")
                    ),
                    "canonical_product_name": clean_text(
                        row.get("canonical_product_name")
                    ),
                    "canonical_set_name": clean_text(
                        row.get("canonical_set_name")
                    ),
                    "governed_candidate_cohort": clean_text(
                        row.get(
                            "governed_candidate_cohort"
                        )
                    ),
                    "scope_state": clean_text(
                        exclusion.get("exclusion_state")
                    ),
                    "scope_exclusion_reason": clean_text(
                        exclusion.get("exclusion_reason")
                    ),
                    "scope_exclusion_basis": clean_text(
                        exclusion.get("exclusion_basis")
                    ),
                    "general_foreign_language_filter_created": False,
                    "selected_sealed_name": clean_text(
                        row.get("selected_sealed_name")
                    ),
                    "selected_sealed_tcgplayer_product_id": clean_text(
                        row.get(
                            "selected_sealed_tcgplayer_product_id"
                        )
                    ),
                    "sealed_match_method": clean_text(
                        row.get("sealed_match_method")
                    ),
                    "sealed_match_state": clean_text(
                        row.get("sealed_match_state")
                    ),
                    "set_release_date": clean_text(
                        row.get("set_release_date")
                    ),
                    "tcgcsv_release_date_candidate": clean_text(
                        row.get(
                            "tcgcsv_release_date_candidate"
                        )
                    ),
                    "product_release_date_candidate": "",
                    "governed_release_date": clean_text(
                        final_release_row.get(
                            "governed_release_date"
                        )
                    ),
                    "governed_release_date_source": clean_text(
                        final_release_row.get(
                            "governed_release_date_source"
                        )
                    ),
                    "governed_release_date_state": clean_text(
                        final_release_row.get(
                            "governed_release_date_state"
                        )
                    ),
                    "release_date_governance_reason": clean_text(
                        final_release_row.get(
                            "release_date_governance_reason"
                        )
                    ),
                    "official_exception_applied": clean_text(
                        final_release_row.get(
                            "official_exception_applied"
                        )
                    ),
                    "final_release_date_assigned": False,
                    "historical_eligibility_decision": (
                        "excluded_by_user_scope"
                    ),
                    "scoring_allowed": False,
                    "universal_investable_allowed": False,
                }
            )

            continue

        active_row = {
            column: clean_text(row.get(column))
            for column in ACTIVE_COLUMNS
        }

        active_row["scope_state"] = (
            "active_historical_review"
        )

        active_row["scope_exclusion_reason"] = ""
        active_row["scope_exclusion_basis"] = ""

        active_row["governed_release_date"] = clean_text(
            final_release_row.get("governed_release_date")
        )

        active_row["governed_release_date_source"] = clean_text(
            final_release_row.get(
                "governed_release_date_source"
            )
        )

        active_row["governed_release_date_state"] = clean_text(
            final_release_row.get(
                "governed_release_date_state"
            )
        )

        active_row["release_date_governance_reason"] = clean_text(
            final_release_row.get(
                "release_date_governance_reason"
            )
        )

        active_row["official_exception_applied"] = clean_text(
            final_release_row.get(
                "official_exception_applied"
            )
        )

        active_row["final_release_date_assigned"] = clean_text(
            final_release_row.get(
                "final_release_date_assigned"
            )
        )

        active_row["historical_eligibility_decision"] = (
            "not_decided"
        )
        active_row["scoring_allowed"] = False
        active_row["universal_investable_allowed"] = False

        active_rows.append(active_row)

    excluded = pd.DataFrame(
        excluded_rows,
        columns=EXCLUSION_COLUMNS,
    )

    active = pd.DataFrame(
        active_rows,
        columns=ACTIVE_COLUMNS,
    )

    if len(excluded) != 1:
        raise RuntimeError(
            "Expected exactly one excluded product row; "
            f"found {len(excluded)}."
        )

    if len(active) != 139:
        raise RuntimeError(
            "Expected 139 active historical review rows; "
            f"found {len(active)}."
        )

    if exclusion_id in set(
        active["canonical_product_id"]
    ):
        raise RuntimeError(
            "Excluded product remains in active review."
        )

    active_assigned = (
        active[
            "final_release_date_assigned"
        ]
        .astype(str)
        .str.strip()
        .str.lower()
        .eq("true")
    )

    if int(active_assigned.sum()) != 139:
        raise RuntimeError(
            "Expected all 139 active products to retain "
            "assigned final release dates."
        )

    if active[
        "governed_release_date"
    ].astype(str).str.strip().eq("").any():
        raise RuntimeError(
            "One or more active products lost the governed "
            "release date."
        )

    active_adjudication = adjudication[
        ~adjudication[
            "canonical_product_id"
        ].isin(exclusions)
    ].copy()

    excluded_adjudication = adjudication[
        adjudication[
            "canonical_product_id"
        ].isin(exclusions)
    ].copy()

    if len(active_adjudication) != 139:
        raise RuntimeError(
            "Expected 139 active adjudication rows; "
            f"found {len(active_adjudication)}."
        )

    if len(excluded_adjudication) != 1:
        raise RuntimeError(
            "Expected one excluded adjudication row."
        )

    active_final_release_index = (
        final_release_dates[
            ~final_release_dates[
                "canonical_product_id"
            ].isin(exclusions)
        ]
        .set_index("canonical_product_id")
    )

    active_adjudication[
        "final_release_date"
    ] = active_adjudication[
        "canonical_product_id"
    ].map(
        active_final_release_index[
            "governed_release_date"
        ]
    )

    active_adjudication[
        "final_release_date_source"
    ] = active_adjudication[
        "canonical_product_id"
    ].map(
        active_final_release_index[
            "governed_release_date_source"
        ]
    )

    active_adjudication[
        "final_release_date_assigned"
    ] = active_adjudication[
        "canonical_product_id"
    ].map(
        active_final_release_index[
            "final_release_date_assigned"
        ]
    )

    active_adjudication[
        "historical_eligibility_decision"
    ] = "not_decided"

    active_adjudication[
        "scoring_allowed"
    ] = False

    active_adjudication[
        "universal_investable_allowed"
    ] = False

    excluded_adjudication[
        "final_release_date"
    ] = ""

    excluded_adjudication[
        "final_release_date_source"
    ] = ""

    excluded_adjudication[
        "final_release_date_assigned"
    ] = False

    if active_adjudication[
        "final_release_date"
    ].astype(str).str.strip().eq("").any():
        raise RuntimeError(
            "Active adjudication contains blank final dates."
        )

    if not active_adjudication[
        "final_release_date_assigned"
    ].astype(str).str.strip().str.lower().eq("true").all():
        raise RuntimeError(
            "Active adjudication did not preserve all "
            "final release-date assignments."
        )

    excluded_adjudication[
        "historical_eligibility_decision"
    ] = "excluded_by_user_scope"

    excluded_adjudication[
        "scoring_allowed"
    ] = False

    excluded_adjudication[
        "universal_investable_allowed"
    ] = False

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    active_path = (
        OUTPUT_ROOT
        / "historical_active_review_population_2026-07-22.csv"
    )

    excluded_path = (
        OUTPUT_ROOT
        / "historical_product_scope_exclusions_2026-07-22.csv"
    )

    active_adjudication_path = (
        OUTPUT_ROOT
        / "historical_active_release_adjudication_2026-07-22.csv"
    )

    excluded_adjudication_path = (
        OUTPUT_ROOT
        / "historical_excluded_release_adjudication_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_product_scope_summary_2026-07-22.json"
    )

    active.to_csv(
        active_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    excluded.to_csv(
        excluded_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    active_adjudication.to_csv(
        active_adjudication_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    excluded_adjudication.to_csv(
        excluded_adjudication_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "scope_resolution_status": "PASS",
        "prior_historical_review_population": 140,
        "product_specific_exclusion_rows": 1,
        "active_historical_review_population": 139,
        "excluded_canonical_product_ids": [
            exclusion_id
        ],
        "excluded_product_names": [
            clean_text(
                exclusion_policy.get(
                    "canonical_product_name"
                )
            )
        ],
        "general_foreign_language_filter_created": False,
        "general_language_policy_created": False,
        "remaining_foreign_language_products_reviewed": False,
        "excluded_product_removed_from_release_adjudication": True,
        "excluded_product_removed_from_performance_analysis": True,
        "excluded_product_removed_from_scoring": True,
        "excluded_product_removed_from_universal_investability": True,
        "final_release_dates_assigned_to_active_rows": 139,
        "active_rows_with_populated_governed_release_dates": 139,
        "active_rows_with_blank_governed_release_dates": 0,
        "final_eligibility_assigned_to_active_rows": False,
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "production_registry_changed": False,
        "universal_database_changed": False,
        "output_files": {
            "active_review_population": (
                repository_relative_path(active_path)
            ),
            "product_scope_exclusions": (
                repository_relative_path(excluded_path)
            ),
            "active_release_adjudication": (
                repository_relative_path(
                    active_adjudication_path
                )
            ),
            "excluded_release_adjudication": (
                repository_relative_path(
                    excluded_adjudication_path
                )
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
        "Phase 10.5R.1D.2.4E.3 "
        "Product-Specific Historical Scope Exclusion"
    )
    print("=" * 76)
    print(
        "Prior historical review population: 140"
    )
    print(
        "Product-specific exclusions: 1"
    )
    print(
        "Active historical review population: 139"
    )
    print(
        "General foreign-language filter created: NO"
    )
    print()
    print(
        "SCOPE RESOLUTION STATUS: PASS"
    )
    print(
        "Final release dates assigned to active products: 139"
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