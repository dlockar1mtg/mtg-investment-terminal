from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

POLICY_PATH = (
    ROOT
    / "config"
    / "historical_premium_booster_eligibility.yaml"
)

HISTORICAL_QUEUE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
    / "historical_booster_review_2026-07-22.csv"
)

GOVERNED_REGISTRY_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
    / "governed_canonical_mtg_registry_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "historical_premium_eligibility"
)

SCHEMA_VERSION = "10.5R.1D.2.1.1"

IDENTITY_COLUMNS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_class",
    "canonical_product_family",
    "canonical_product_type",
    "canonical_packaging_level",
]

AUDIT_COLUMNS = [
    *IDENTITY_COLUMNS,
    "matched_governed_registry",
    "available_evidence_fields",
    "available_evidence_field_count",
    "release_timing_evidence",
    "pricing_evidence",
    "liquidity_evidence",
    "supply_evidence",
    "premium_name_indicator",
    "mass_market_name_indicator",
    "premium_name_matches",
    "mass_market_name_matches",
    "evidence_state",
    "evidence_notes",
    "historical_eligibility_decision",
    "historical_decision_reason",
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
    with POLICY_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        policy = yaml.safe_load(handle)

    if not isinstance(policy, dict):
        raise ValueError(
            "Historical eligibility policy must be a mapping."
        )

    if policy.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(
            "Historical eligibility policy version mismatch."
        )

    return policy


def configured_fields(
    policy: dict[str, Any],
    group: str,
) -> list[str]:
    requirements = policy.get(
        "evidence_requirements",
        {},
    )

    preferred = requirements.get(
        "preferred_fields",
        {},
    )

    values = preferred.get(
        group,
        [],
    )

    return [
        clean_text(value)
        for value in values
        if clean_text(value)
    ]


def populated_fields(
    row: pd.Series,
    candidates: list[str],
) -> list[str]:
    return [
        field
        for field in candidates
        if field in row.index
        and clean_text(row.get(field))
    ]


def pattern_matches(
    product_name: str,
    patterns: list[str],
) -> list[str]:
    normalized = product_name.casefold()

    return [
        pattern
        for pattern in patterns
        if pattern.casefold() in normalized
    ]


def evidence_state(
    *,
    timing_fields: list[str],
    pricing_fields: list[str],
    liquidity_fields: list[str],
    supply_fields: list[str],
) -> tuple[str, str]:
    evidence_groups = {
        "release_timing": bool(timing_fields),
        "pricing": bool(pricing_fields),
        "liquidity": bool(liquidity_fields),
        "supply": bool(supply_fields),
    }

    available_groups = [
        name
        for name, available in evidence_groups.items()
        if available
    ]

    missing_groups = [
        name
        for name, available in evidence_groups.items()
        if not available
    ]

    if len(available_groups) == 4:
        return (
            "evidence_complete",
            "all_required_evidence_groups_available",
        )

    if available_groups:
        return (
            "evidence_partial",
            (
                "available:"
                + "|".join(available_groups)
                + ";missing:"
                + "|".join(missing_groups)
            ),
        )

    return (
        "external_enrichment_required",
        (
            "missing:"
            + "|".join(missing_groups)
        ),
    )


def build_audit(
    *,
    historical: pd.DataFrame,
    governed: pd.DataFrame,
    policy: dict[str, Any],
) -> pd.DataFrame:
    governed_index = governed.set_index(
        "canonical_product_id",
        drop=False,
    )

    timing_candidates = configured_fields(
        policy,
        "timing",
    )

    pricing_candidates = configured_fields(
        policy,
        "pricing",
    )

    liquidity_candidates = configured_fields(
        policy,
        "liquidity",
    )

    supply_candidates = configured_fields(
        policy,
        "supply",
    )

    premium_patterns = (
        policy.get(
            "premium_product_indicators",
            {},
        ).get(
            "name_patterns",
            [],
        )
    )

    mass_market_patterns = (
        policy.get(
            "mass_market_indicators",
            {},
        ).get(
            "name_patterns",
            [],
        )
    )

    output_rows: list[dict[str, Any]] = []

    for _, historical_row in historical.iterrows():
        canonical_id = clean_text(
            historical_row.get(
                "canonical_product_id"
            )
        )

        matched = (
            canonical_id in governed_index.index
        )

        if matched:
            governed_row = governed_index.loc[
                canonical_id
            ]

            if isinstance(
                governed_row,
                pd.DataFrame,
            ):
                governed_row = governed_row.iloc[0]
        else:
            governed_row = historical_row

        timing_fields = populated_fields(
            governed_row,
            timing_candidates,
        )

        pricing_fields = populated_fields(
            governed_row,
            pricing_candidates,
        )

        liquidity_fields = populated_fields(
            governed_row,
            liquidity_candidates,
        )

        supply_fields = populated_fields(
            governed_row,
            supply_candidates,
        )

        all_evidence_fields = sorted(
            set(
                timing_fields
                + pricing_fields
                + liquidity_fields
                + supply_fields
            )
        )

        product_name = clean_text(
            historical_row.get(
                "canonical_product_name"
            )
        )

        premium_matches = pattern_matches(
            product_name,
            premium_patterns,
        )

        mass_market_matches = pattern_matches(
            product_name,
            mass_market_patterns,
        )

        state, notes = evidence_state(
            timing_fields=timing_fields,
            pricing_fields=pricing_fields,
            liquidity_fields=liquidity_fields,
            supply_fields=supply_fields,
        )

        output_row: dict[str, Any] = {}

        for column in IDENTITY_COLUMNS:
            output_row[column] = clean_text(
                historical_row.get(column)
            )

        output_row.update(
            {
                "matched_governed_registry": matched,
                "available_evidence_fields": "|".join(
                    all_evidence_fields
                ),
                "available_evidence_field_count": len(
                    all_evidence_fields
                ),
                "release_timing_evidence": "|".join(
                    timing_fields
                ),
                "pricing_evidence": "|".join(
                    pricing_fields
                ),
                "liquidity_evidence": "|".join(
                    liquidity_fields
                ),
                "supply_evidence": "|".join(
                    supply_fields
                ),
                "premium_name_indicator": bool(
                    premium_matches
                ),
                "mass_market_name_indicator": bool(
                    mass_market_matches
                ),
                "premium_name_matches": "|".join(
                    premium_matches
                ),
                "mass_market_name_matches": "|".join(
                    mass_market_matches
                ),
                "evidence_state": state,
                "evidence_notes": notes,
                "historical_eligibility_decision": (
                    "not_decided"
                ),
                "historical_decision_reason": "",
                "scoring_allowed": False,
                "universal_investable_allowed": False,
            }
        )

        output_rows.append(output_row)

    return (
        pd.DataFrame(
            output_rows,
            columns=AUDIT_COLUMNS,
        )
        .sort_values(
            [
                "evidence_state",
                "canonical_product_type",
                "canonical_product_name",
                "canonical_product_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


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


def main() -> int:
    policy = load_policy()

    if not HISTORICAL_QUEUE_PATH.is_file():
        raise FileNotFoundError(
            "Historical review queue not found: "
            f"{HISTORICAL_QUEUE_PATH}"
        )

    if not GOVERNED_REGISTRY_PATH.is_file():
        raise FileNotFoundError(
            "Governed canonical registry not found: "
            f"{GOVERNED_REGISTRY_PATH}"
        )

    historical = pd.read_csv(
        HISTORICAL_QUEUE_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    governed = pd.read_csv(
        GOVERNED_REGISTRY_PATH,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    expected_rows = int(
        policy.get(
            "scope",
            {},
        ).get(
            "expected_input_rows",
            0,
        )
    )

    if len(historical) != expected_rows:
        raise RuntimeError(
            "Expected "
            f"{expected_rows} historical review rows; "
            f"found {len(historical)}."
        )

    if historical[
        "canonical_product_id"
    ].duplicated().any():
        raise RuntimeError(
            "Historical review queue contains duplicate canonical IDs."
        )

    audit = build_audit(
        historical=historical,
        governed=governed,
        policy=policy,
    )

    if len(audit) != expected_rows:
        raise RuntimeError(
            "Historical enrichment audit row count mismatch."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_path = (
        OUTPUT_ROOT
        / "historical_premium_enrichment_audit_2026-07-22.csv"
    )

    external_queue_path = (
        OUTPUT_ROOT
        / "historical_external_enrichment_queue_2026-07-22.csv"
    )

    premium_indicator_path = (
        OUTPUT_ROOT
        / "historical_premium_name_candidates_2026-07-22.csv"
    )

    mass_market_path = (
        OUTPUT_ROOT
        / "historical_mass_market_name_candidates_2026-07-22.csv"
    )

    coverage_path = (
        OUTPUT_ROOT
        / "historical_evidence_field_coverage_2026-07-22.csv"
    )

    summary_path = (
        OUTPUT_ROOT
        / "historical_premium_enrichment_summary_2026-07-22.json"
    )

    external_queue = audit[
        audit["evidence_state"].isin(
            {
                "external_enrichment_required",
                "evidence_partial",
            }
        )
    ].copy()

    premium_candidates = audit[
        audit[
            "premium_name_indicator"
        ].eq(True)
    ].copy()

    mass_market_candidates = audit[
        audit[
            "mass_market_name_indicator"
        ].eq(True)
    ].copy()

    governed_columns = set(
        governed.columns
    )

    configured_groups = {
        "timing": configured_fields(
            policy,
            "timing",
        ),
        "pricing": configured_fields(
            policy,
            "pricing",
        ),
        "liquidity": configured_fields(
            policy,
            "liquidity",
        ),
        "supply": configured_fields(
            policy,
            "supply",
        ),
    }

    coverage_rows: list[dict[str, Any]] = []

    for group, fields in configured_groups.items():
        for field in fields:
            field_exists = field in governed_columns

            populated_count = (
                int(
                    governed[field]
                    .astype(str)
                    .str.strip()
                    .ne("")
                    .sum()
                )
                if field_exists
                else 0
            )

            coverage_rows.append(
                {
                    "evidence_group": group,
                    "field_name": field,
                    "field_exists": field_exists,
                    "governed_registry_populated_rows": (
                        populated_count
                    ),
                    "historical_audit_rows_using_field": int(
                        audit[
                            "available_evidence_fields"
                        ]
                        .str.split("|")
                        .apply(
                            lambda values: (
                                field in values
                                if isinstance(
                                    values,
                                    list,
                                )
                                else False
                            )
                        )
                        .sum()
                    ),
                }
            )

    coverage = pd.DataFrame(
        coverage_rows
    )

    write_csv(
        audit,
        audit_path,
    )

    write_csv(
        external_queue,
        external_queue_path,
    )

    write_csv(
        premium_candidates,
        premium_indicator_path,
    )

    write_csv(
        mass_market_candidates,
        mass_market_path,
    )

    write_csv(
        coverage,
        coverage_path,
    )

    evidence_counts = {
        str(key): int(value)
        for key, value in (
            audit["evidence_state"]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    product_type_counts = {
        str(key): int(value)
        for key, value in (
            audit["canonical_product_type"]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "audit_status": "PASS",
        "historical_input_rows": int(
            len(historical)
        ),
        "historical_audit_rows": int(
            len(audit)
        ),
        "unique_canonical_product_ids": int(
            audit[
                "canonical_product_id"
            ].nunique()
        ),
        "governed_registry_match_rows": int(
            audit[
                "matched_governed_registry"
            ].eq(True).sum()
        ),
        "evidence_state_counts": evidence_counts,
        "product_type_counts": product_type_counts,
        "external_enrichment_queue_rows": int(
            len(external_queue)
        ),
        "premium_name_candidate_rows": int(
            len(premium_candidates)
        ),
        "mass_market_name_candidate_rows": int(
            len(mass_market_candidates)
        ),
        "final_eligible_rows": 0,
        "final_ineligible_rows": 0,
        "not_decided_rows": int(
            len(audit)
        ),
        "scoring_allowed_rows": 0,
        "universal_investable_allowed_rows": 0,
        "input_files": {
            "policy": str(POLICY_PATH),
            "historical_review_queue": str(
                HISTORICAL_QUEUE_PATH
            ),
            "governed_registry": str(
                GOVERNED_REGISTRY_PATH
            ),
        },
        "output_files": {
            "enrichment_audit": str(
                audit_path
            ),
            "external_enrichment_queue": str(
                external_queue_path
            ),
            "premium_name_candidates": str(
                premium_indicator_path
            ),
            "mass_market_name_candidates": str(
                mass_market_path
            ),
            "field_coverage": str(
                coverage_path
            ),
        },
        "structural_audit_changed": False,
        "canonical_registry_changed": False,
        "governed_registry_changed": False,
        "production_registry_changed": False,
        "final_eligibility_assigned": False,
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
        "Phase 10.5R.1D.2.1 "
        "Historical Premium Enrichment Audit"
    )
    print("=" * 76)
    print(
        f"Historical input rows: {len(historical)}"
    )
    print(
        f"Historical audit rows: {len(audit)}"
    )
    print(
        "Unique canonical IDs: "
        f"{audit['canonical_product_id'].nunique()}"
    )
    print(
        "Governed registry matches: "
        f"{audit['matched_governed_registry'].eq(True).sum()}"
    )
    print()

    for state, count in sorted(
        evidence_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{state}: {count}"
        )

    print()
    print(
        "Premium name candidates: "
        f"{len(premium_candidates)}"
    )
    print(
        "Mass-market name candidates: "
        f"{len(mass_market_candidates)}"
    )
    print(
        "External enrichment queue: "
        f"{len(external_queue)}"
    )
    print()
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
        "PHASE 10.5R.1D.2.1 "
        "ENRICHMENT AUDIT: PASS"
    )
    print(
        "Final eligibility: NOT ASSIGNED"
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