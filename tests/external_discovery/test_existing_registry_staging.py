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
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
)


def load_summary() -> dict:
    return json.loads(
        (
            VALIDATION_ROOT
            / "existing_registry_staging_summary.json"
        ).read_text(encoding="utf-8")
    )


def load_stage() -> pd.DataFrame:
    return pd.read_csv(
        STAGING_ROOT
        / "existing_registry_canonical_stage.csv",
        low_memory=False,
    )


def test_all_existing_registry_records_are_preserved() -> None:
    summary = load_summary()

    assert summary["source_row_count"] == 4675
    assert summary["staged_row_count"] == 4675

    assert summary["invariants"][
        "all_source_rows_preserved"
    ]
    assert summary["invariants"][
        "source_ids_unique"
    ]
    assert summary["invariants"][
        "stage_ids_unique"
    ]
    assert summary["invariants"][
        "approval_status_preserved"
    ]


def test_source_approval_statuses_are_unchanged() -> None:
    summary = load_summary()

    assert summary["approval_status_counts"] == {
        "approved": 234,
        "review_required": 4441,
    }

    assert summary["approved_snapshot_count"] == 234


def test_product_family_totals_reconcile() -> None:
    summary = load_summary()

    assert summary["product_family_counts"] == {
        "booster_display": 348,
        "secret_lair": 4327,
    }

    assert (
        sum(
            summary[
                "product_family_counts"
            ].values()
        )
        == 4675
    )


def test_product_subtype_totals_reconcile() -> None:
    summary = load_summary()

    expected = {
        "collector_booster_display": 77,
        "draft_booster_display": 42,
        "jumpstart_booster_display": 15,
        "masters_booster_display": 19,
        "secret_lair_drop": 4327,
        "theme_booster_display": 18,
        "traditional_booster_display": 177,
    }

    assert summary["product_subtype_counts"] == expected
    assert sum(expected.values()) == 4675


def test_stage_contains_required_canonical_columns() -> None:
    frame = load_stage()

    required_columns = {
        "canonical_stage_id",
        "source_system",
        "source_record_id",
        "investment_product_id",
        "tcgplayer_product_id",
        "source_set_name",
        "source_product_name",
        "source_product_type",
        "source_approval_status",
        "normalized_set_name",
        "normalized_product_name",
        "normalized_match_name",
        "canonical_product_family",
        "canonical_product_subtype",
        "language",
        "foil_variant",
        "edition_variant",
        "duplicate_group_key",
        "duplicate_group_size",
        "staging_status",
        "review_reason",
    }

    assert required_columns.issubset(
        set(frame.columns)
    )


def test_stage_ids_and_source_ids_are_unique() -> None:
    frame = load_stage()

    assert len(frame) == 4675
    assert frame["canonical_stage_id"].nunique() == 4675
    assert frame["source_record_id"].nunique() == 4675
    assert frame["tcgplayer_product_id"].nunique() == 4675


def test_no_record_is_unclassified() -> None:
    summary = load_summary()
    frame = load_stage()

    assert summary["unclassified_count"] == 0

    assert not frame[
        "canonical_product_family"
    ].eq("unclassified").any()

    assert not frame[
        "canonical_product_subtype"
    ].eq("unclassified").any()


def test_staging_does_not_change_eligibility() -> None:
    summary = load_summary()

    assert summary["certification_status"] == (
        "STAGING_COMPLETE_NOT_ELIGIBILITY_CERTIFIED"
    )

    frame = load_stage()

    assert "eligibility_status" not in frame.columns
    assert "investment_class" not in frame.columns