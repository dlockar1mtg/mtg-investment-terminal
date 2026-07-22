from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

STAGING_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "reconciliation"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "reconciliation"
)

RECONCILIATION_PATH = (
    STAGING_ROOT
    / "tcgcsv_candidate_reconciliation_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_candidate_reconciliation_summary_2026-07-22.json"
)

NEW_CANDIDATES_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_new_candidates_2026-07-22.csv"
)

REVIEW_QUEUE_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_reconciliation_review_queue_2026-07-22.csv"
)

CONFLICT_PATH = (
    VALIDATION_ROOT
    / "tcgcsv_type_conflicts_2026-07-22.csv"
)


def load_summary() -> dict[str, object]:
    return json.loads(
        SUMMARY_PATH.read_text(
            encoding="utf-8"
        )
    )


def test_reconciliation_totals() -> None:
    summary = load_summary()

    assert summary["candidate_rows"] == 5239
    assert summary["registry_rows"] == 4675
    assert summary["reconciled_rows"] == 5239
    assert (
        summary[
            "unique_candidate_record_ids"
        ]
        == 5239
    )
    assert (
        summary[
            "unique_candidate_product_ids"
        ]
        == 5239
    )


def test_reconciliation_outcomes() -> None:
    summary = load_summary()

    assert (
        summary[
            "exact_id_match_rows"
        ]
        == 4674
    )

    assert (
        summary[
            "new_candidate_rows"
        ]
        == 565
    )

    assert (
        summary[
            "normalized_name_match_rows"
        ]
        == 0
    )

    assert (
        summary[
            "ambiguous_or_missing_id_rows"
        ]
        == 0
    )


def test_all_secret_lair_records_remain_included() -> None:
    reconciliation = pd.read_csv(
        RECONCILIATION_PATH,
        low_memory=False,
    )

    secret_lair = reconciliation[
        reconciliation[
            "candidate_class"
        ].eq("secret_lair_product")
    ]

    assert len(secret_lair) == 4347

    compatible_generic = secret_lair[
        secret_lair[
            "type_alignment"
        ].eq(
            "compatible_registry_generic_"
            "secret_lair"
        )
    ]

    assert len(compatible_generic) == 4072

    assert compatible_generic[
        "reconciliation_status"
    ].eq("exact_id_match").all()


def test_generic_booster_display_compatibility() -> None:
    reconciliation = pd.read_csv(
        RECONCILIATION_PATH,
        low_memory=False,
    )

    records = reconciliation[
        reconciliation[
            "type_alignment"
        ].eq(
            "compatible_registry_generic_"
            "booster_display"
        )
    ]

    assert len(records) == 27
    assert records[
        "reconciliation_status"
    ].eq("exact_id_match").all()


def test_case_packaging_compatibility() -> None:
    reconciliation = pd.read_csv(
        RECONCILIATION_PATH,
        low_memory=False,
    )

    records = reconciliation[
        reconciliation[
            "type_alignment"
        ].eq(
            "compatible_registry_generic_"
            "case_packaging"
        )
    ]

    assert len(records) == 90

    assert records[
        "candidate_type_family"
    ].eq("sealed_case").all()

    assert records[
        "reconciliation_status"
    ].eq("exact_id_match").all()


def test_new_candidate_breakdown() -> None:
    new_candidates = pd.read_csv(
        NEW_CANDIDATES_PATH,
        low_memory=False,
    )

    assert len(new_candidates) == 565

    counts = (
        new_candidates[
            "candidate_class"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "sealed_product": 544,
        "secret_lair_product": 21,
    }


def test_no_unresolved_review_records() -> None:
    review_queue = pd.read_csv(
        REVIEW_QUEUE_PATH,
        low_memory=False,
    )

    conflicts = pd.read_csv(
        CONFLICT_PATH,
        low_memory=False,
    )

    assert review_queue.empty
    assert conflicts.empty

    summary = load_summary()

    assert (
        summary[
            "review_queue_rows"
        ]
        == 0
    )

    assert (
        summary[
            "type_conflict_or_review_rows"
        ]
        == 0
    )


def test_reconciliation_does_not_mutate_platform() -> None:
    summary = load_summary()

    assert (
        summary[
            "eligibility_changed"
        ]
        is False
    )

    assert (
        summary[
            "approval_status_changed"
        ]
        is False
    )

    assert (
        summary[
            "registry_changed"
        ]
        is False
    )

    assert (
        summary[
            "database_changed"
        ]
        is False
    )

    assert (
        summary[
            "scoring_applied"
        ]
        is False
    )

    assert (
        summary[
            "buy_recommendations_created"
        ]
        is False
    )