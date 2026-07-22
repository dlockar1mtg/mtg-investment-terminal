from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

TCGCSV_EVIDENCE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_secret_lair_product_evidence_2026-07-22.csv"
)

STRUCTURAL_CANDIDATES_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
    / "secret_lair_structural_candidates_2026-07-22.csv"
)

STAGING_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

REGISTRY_SEED_PATH = (
    STAGING_ROOT
    / "secret_lair_registry_seed_2026-07-22.csv"
)

EVIDENCE_MATCHES_PATH = (
    VALIDATION_ROOT
    / "secret_lair_evidence_matches_2026-07-22.csv"
)

UNMATCHED_PATH = (
    VALIDATION_ROOT
    / "secret_lair_unmatched_structural_candidates_2026-07-22.csv"
)

DUPLICATES_PATH = (
    VALIDATION_ROOT
    / "secret_lair_duplicate_marketplace_evidence_2026-07-22.csv"
)

NONSTRUCTURAL_PATH = (
    VALIDATION_ROOT
    / "secret_lair_nonstructural_marketplace_evidence_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_catalog_reconstruction_summary_2026-07-22.json"
)

REGISTRY_COLUMNS = [
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
    "historical_review_required",
    "sealed_product_review_required",
    "classification_review_required",
    "tcgcsv_snapshot_record_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "tcgcsv_group_name",
    "tcgcsv_group_published_on",
    "tcgcsv_product_name",
    "tcgcsv_evidence_class",
    "tcgcsv_sealed_drop_status",
    "tcgcsv_review_reason",
    "marketplace_evidence_match_count",
    "marketplace_identity_state",
    "final_eligibility_decision",
    "final_decision_reason",
    "scoring_allowed",
    "universal_investable_allowed",
]


def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalized_id(value: Any) -> str:
    text = clean(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required input is missing: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return [
            {
                clean(key): clean(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str],
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
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    column: row.get(column, "")
                    for column in columns
                }
            )


def parse_bool(value: Any) -> bool:
    return clean(value).lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def main() -> int:
    evidence = read_csv(TCGCSV_EVIDENCE_PATH)
    structural = read_csv(STRUCTURAL_CANDIDATES_PATH)

    if not evidence:
        raise RuntimeError(
            "TCGCSV Secret Lair evidence is empty."
        )

    if not structural:
        raise RuntimeError(
            "Secret Lair structural candidate input is empty."
        )

    evidence_required = {
        "snapshot_record_id",
        "tcgcsv_category_id",
        "tcgcsv_group_id",
        "tcgplayer_product_id",
        "group_name",
        "group_published_on",
        "product_name",
        "evidence_class",
        "sealed_drop_status",
        "review_reason",
    }

    structural_required = {
        "canonical_product_id",
        "tcgplayer_product_id",
        "canonical_set_name",
        "canonical_product_name",
        "structural_eligibility_state",
        "final_eligibility_decision",
        "scoring_allowed",
        "universal_investable_allowed",
    }

    evidence_columns = set(evidence[0])
    structural_columns = set(structural[0])

    missing_evidence_columns = sorted(
        evidence_required - evidence_columns
    )

    missing_structural_columns = sorted(
        structural_required - structural_columns
    )

    if missing_evidence_columns:
        raise RuntimeError(
            "TCGCSV evidence is missing required columns: "
            + ", ".join(missing_evidence_columns)
        )

    if missing_structural_columns:
        raise RuntimeError(
            "Structural candidate input is missing required columns: "
            + ", ".join(missing_structural_columns)
        )

    canonical_ids = [
        clean(row.get("canonical_product_id"))
        for row in structural
    ]

    canonical_ids_nonblank = [
        value
        for value in canonical_ids
        if value
    ]

    if len(canonical_ids_nonblank) != len(
        set(canonical_ids_nonblank)
    ):
        raise RuntimeError(
            "Structural candidates contain duplicate "
            "canonical product IDs."
        )

    structural_tcgplayer_ids = [
        normalized_id(
            row.get("tcgplayer_product_id")
        )
        for row in structural
    ]

    nonblank_structural_tcgplayer_ids = [
        value
        for value in structural_tcgplayer_ids
        if value
    ]

    if len(nonblank_structural_tcgplayer_ids) != len(
        set(nonblank_structural_tcgplayer_ids)
    ):
        raise RuntimeError(
            "Structural candidates contain duplicate "
            "TCGplayer product IDs."
        )

    evidence_by_product_id: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for row in evidence:
        product_id = normalized_id(
            row.get("tcgplayer_product_id")
        )

        if not product_id:
            continue

        evidence_by_product_id.setdefault(
            product_id,
            [],
        ).append(row)

    duplicate_evidence_rows: list[
        dict[str, Any]
    ] = []

    for product_id, matches in sorted(
        evidence_by_product_id.items()
    ):
        if len(matches) <= 1:
            continue

        for match in matches:
            duplicate_evidence_rows.append(
                {
                    **match,
                    "evidence_match_count": len(matches),
                }
            )

    registry_rows: list[dict[str, Any]] = []
    matched_evidence_rows: list[
        dict[str, Any]
    ] = []
    unmatched_rows: list[dict[str, Any]] = []

    structural_id_set = set(
        nonblank_structural_tcgplayer_ids
    )

    for structural_row in structural:
        product_id = normalized_id(
            structural_row.get(
                "tcgplayer_product_id"
            )
        )

        matches = evidence_by_product_id.get(
            product_id,
            [],
        )

        selected_match = (
            matches[0]
            if matches
            else {}
        )

        match_count = len(matches)

        if match_count == 0:
            marketplace_identity_state = (
                "tcgcsv_evidence_missing"
            )

            unmatched_rows.append(
                dict(structural_row)
            )

        elif match_count == 1:
            marketplace_identity_state = (
                "exact_tcgplayer_id_match"
            )

        else:
            marketplace_identity_state = (
                "duplicate_tcgplayer_id_evidence_review"
            )

        if selected_match:
            matched_evidence_rows.append(
                {
                    "canonical_product_id": clean(
                        structural_row.get(
                            "canonical_product_id"
                        )
                    ),
                    "canonical_product_name": clean(
                        structural_row.get(
                            "canonical_product_name"
                        )
                    ),
                    "canonical_set_name": clean(
                        structural_row.get(
                            "canonical_set_name"
                        )
                    ),
                    "tcgplayer_product_id": product_id,
                    **selected_match,
                    "evidence_match_count": (
                        match_count
                    ),
                    "marketplace_identity_state": (
                        marketplace_identity_state
                    ),
                }
            )

        registry_row = {
            column: clean(
                structural_row.get(column)
            )
            for column in REGISTRY_COLUMNS
        }

        registry_row.update(
            {
                "tcgplayer_product_id": product_id,
                "tcgcsv_snapshot_record_id": clean(
                    selected_match.get(
                        "snapshot_record_id"
                    )
                ),
                "tcgcsv_category_id": clean(
                    selected_match.get(
                        "tcgcsv_category_id"
                    )
                ),
                "tcgcsv_group_id": clean(
                    selected_match.get(
                        "tcgcsv_group_id"
                    )
                ),
                "tcgcsv_group_name": clean(
                    selected_match.get(
                        "group_name"
                    )
                ),
                "tcgcsv_group_published_on": clean(
                    selected_match.get(
                        "group_published_on"
                    )
                ),
                "tcgcsv_product_name": clean(
                    selected_match.get(
                        "product_name"
                    )
                ),
                "tcgcsv_evidence_class": clean(
                    selected_match.get(
                        "evidence_class"
                    )
                ),
                "tcgcsv_sealed_drop_status": clean(
                    selected_match.get(
                        "sealed_drop_status"
                    )
                ),
                "tcgcsv_review_reason": clean(
                    selected_match.get(
                        "review_reason"
                    )
                ),
                "marketplace_evidence_match_count": (
                    match_count
                ),
                "marketplace_identity_state": (
                    marketplace_identity_state
                ),
                "final_eligibility_decision": (
                    "not_decided"
                ),
                "final_decision_reason": (
                    "Secret Lair reconstruction "
                    "and evidence certification pending."
                ),
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

        registry_rows.append(registry_row)

    nonstructural_rows = [
        row
        for row in evidence
        if normalized_id(
            row.get("tcgplayer_product_id")
        )
        not in structural_id_set
    ]

    registry_rows = sorted(
        registry_rows,
        key=lambda row: (
            clean(
                row.get("canonical_set_name")
            ).lower(),
            clean(
                row.get("canonical_product_name")
            ).lower(),
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
        ),
    )

    matched_evidence_rows = sorted(
        matched_evidence_rows,
        key=lambda row: (
            clean(
                row.get("canonical_product_name")
            ).lower(),
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
        ),
    )

    unmatched_rows = sorted(
        unmatched_rows,
        key=lambda row: (
            clean(
                row.get("canonical_product_name")
            ).lower(),
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
        ),
    )

    duplicate_evidence_rows = sorted(
        duplicate_evidence_rows,
        key=lambda row: (
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
            clean(
                row.get("snapshot_record_id")
            ),
        ),
    )

    nonstructural_rows = sorted(
        nonstructural_rows,
        key=lambda row: (
            clean(
                row.get("group_name")
            ).lower(),
            clean(
                row.get("product_name")
            ).lower(),
            normalized_id(
                row.get("tcgplayer_product_id")
            ),
        ),
    )

    write_csv(
        REGISTRY_SEED_PATH,
        registry_rows,
        REGISTRY_COLUMNS,
    )

    evidence_match_columns = [
        "canonical_product_id",
        "canonical_product_name",
        "canonical_set_name",
        "tcgplayer_product_id",
        "snapshot_record_id",
        "tcgcsv_category_id",
        "tcgcsv_group_id",
        "group_name",
        "group_published_on",
        "product_name",
        "evidence_class",
        "sealed_drop_status",
        "review_reason",
        "evidence_match_count",
        "marketplace_identity_state",
    ]

    write_csv(
        EVIDENCE_MATCHES_PATH,
        matched_evidence_rows,
        evidence_match_columns,
    )

    write_csv(
        UNMATCHED_PATH,
        unmatched_rows,
        list(structural[0].keys()),
    )

    write_csv(
        DUPLICATES_PATH,
        duplicate_evidence_rows,
        list(evidence[0].keys())
        + ["evidence_match_count"],
    )

    write_csv(
        NONSTRUCTURAL_PATH,
        nonstructural_rows,
        list(evidence[0].keys()),
    )

    structural_state_counts = Counter(
        clean(
            row.get(
                "structural_eligibility_state"
            )
        )
        or "blank"
        for row in structural
    )

    evidence_class_counts = Counter(
        clean(row.get("evidence_class"))
        or "blank"
        for row in evidence
    )

    sealed_status_counts = Counter(
        clean(row.get("sealed_drop_status"))
        or "blank"
        for row in evidence
    )

    identity_state_counts = Counter(
        clean(
            row.get(
                "marketplace_identity_state"
            )
        )
        or "blank"
        for row in registry_rows
    )

    audit_status = (
        "PASS"
        if not unmatched_rows
        and not duplicate_evidence_rows
        else "PARTIAL"
    )

    summary = {
        "schema_version": "10.5R.3.2",
        "generated_at_utc": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "audit_status": audit_status,
        "tcgcsv_evidence_rows": len(evidence),
        "tcgcsv_unique_product_ids": len(
            evidence_by_product_id
        ),
        "structural_candidate_rows": len(
            structural
        ),
        "structural_unique_canonical_ids": len(
            set(canonical_ids_nonblank)
        ),
        "structural_unique_tcgplayer_ids": len(
            set(
                nonblank_structural_tcgplayer_ids
            )
        ),
        "registry_seed_rows": len(registry_rows),
        "matched_structural_candidates": len(
            matched_evidence_rows
        ),
        "unmatched_structural_candidates": len(
            unmatched_rows
        ),
        "duplicate_marketplace_evidence_rows": (
            len(duplicate_evidence_rows)
        ),
        "nonstructural_marketplace_evidence_rows": (
            len(nonstructural_rows)
        ),
        "structural_eligibility_state_counts": (
            dict(
                sorted(
                    structural_state_counts.items()
                )
            )
        ),
        "evidence_class_counts": dict(
            sorted(
                evidence_class_counts.items()
            )
        ),
        "sealed_drop_status_counts": dict(
            sorted(
                sealed_status_counts.items()
            )
        ),
        "marketplace_identity_state_counts": dict(
            sorted(
                identity_state_counts.items()
            )
        ),
        "governance": {
            "production_registry_changed": False,
            "universal_database_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "registry_seed": (
                REGISTRY_SEED_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "evidence_matches": (
                EVIDENCE_MATCHES_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "unmatched_candidates": (
                UNMATCHED_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "duplicate_evidence": (
                DUPLICATES_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "nonstructural_evidence": (
                NONSTRUCTURAL_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
        },
    }

    SUMMARY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SUMMARY_PATH.write_text(
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
        "Phase 10.5R.3.2 Secret Lair "
        "Catalog Reconstruction"
    )
    print("=" * 76)
    print(
        f"TCGCSV evidence rows: {len(evidence)}"
    )
    print(
        "TCGCSV unique product IDs: "
        f"{len(evidence_by_product_id)}"
    )
    print(
        "Governed structural candidates: "
        f"{len(structural)}"
    )
    print(
        "Registry seed rows: "
        f"{len(registry_rows)}"
    )
    print(
        "Exact evidence matches: "
        f"{len(matched_evidence_rows)}"
    )
    print(
        "Unmatched candidates: "
        f"{len(unmatched_rows)}"
    )
    print(
        "Duplicate evidence rows: "
        f"{len(duplicate_evidence_rows)}"
    )
    print(
        "Nonstructural evidence rows: "
        f"{len(nonstructural_rows)}"
    )
    print()
    print(
        "Marketplace identity states:"
    )

    for state, count in sorted(
        identity_state_counts.items()
    ):
        print(f"  {state}: {count}")

    print()
    print(
        "CATALOG RECONSTRUCTION STATUS: "
        + audit_status
    )
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print("Production registry changed: NO")
    print("Universal database changed: NO")
    print()
    print(
        "Summary: "
        + SUMMARY_PATH
        .relative_to(ROOT)
        .as_posix()
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())