from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_PATH = (
    ROOT
    / "scripts"
    / "external_discovery"
    / "validate_canonical_registry_refresh.py"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "canonical_registry_refresh"
)

REPORT_PATH = (
    VALIDATION_ROOT
    / "canonical_registry_change_report_2026-07-22.csv"
)

REVIEW_PATH = (
    VALIDATION_ROOT
    / "canonical_registry_change_review_queue_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "canonical_registry_refresh_summary_2026-07-22.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "refresh_control",
        SCRIPT_PATH,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(module)

    return module


def base_prior_row() -> dict[str, str]:
    return {
        "canonical_product_id": (
            "MTG-CANON-TCGPLAYER-100"
        ),
        "tcgplayer_product_id": "100",
        "canonical_product_name": (
            "Example Booster Box"
        ),
        "canonical_product_class": (
            "sealed_product"
        ),
        "canonical_product_family": (
            "booster_display"
        ),
        "canonical_product_type": (
            "traditional_booster_display"
        ),
        "canonical_packaging_level": (
            "display"
        ),
        "identity_lifecycle_status": (
            "active"
        ),
        "source_availability_status": (
            "available"
        ),
    }


def base_current_row() -> dict[str, str]:
    row = base_prior_row()

    row.pop(
        "identity_lifecycle_status"
    )

    row.pop(
        "source_availability_status"
    )

    return row


def build_report(
    prior_rows: list[dict[str, str]],
    current_rows: list[dict[str, str]],
) -> pd.DataFrame:
    module = load_module()

    return module.build_change_report(
        pd.DataFrame(prior_rows),
        pd.DataFrame(current_rows),
    )


def test_baseline_refresh_summary_passes() -> None:
    summary = json.loads(
        SUMMARY_PATH.read_text(
            encoding="utf-8"
        )
    )

    assert (
        summary[
            "refresh_validation_status"
        ]
        == "PASS"
    )

    assert (
        summary["comparison_rows"]
        == 5239
    )

    assert (
        summary["unchanged_rows"]
        == 5239
    )

    assert (
        summary["change_report_rows"]
        == 0
    )

    assert (
        summary["review_queue_rows"]
        == 0
    )


def test_baseline_exception_files_are_empty() -> None:
    report = pd.read_csv(
        REPORT_PATH,
        dtype=str,
        keep_default_na=False,
    )

    review = pd.read_csv(
        REVIEW_PATH,
        dtype=str,
        keep_default_na=False,
    )

    assert report.empty
    assert review.empty


def test_unchanged_identity() -> None:
    report = build_report(
        [base_prior_row()],
        [base_current_row()],
    )

    assert len(report) == 1

    row = report.iloc[0]

    assert row["change_type"] == (
        "unchanged"
    )

    assert bool(
        row["review_required"]
    ) is False

    assert (
        row[
            "resulting_lifecycle_status"
        ]
        == "active"
    )

    assert (
        row[
            "resulting_source_availability"
        ]
        == "available"
    )


def test_new_identity_requires_review() -> None:
    current = base_current_row()

    report = build_report(
        [],
        [current],
    )

    row = report.iloc[0]

    assert row["change_type"] == (
        "new_identity"
    )

    assert bool(
        row["review_required"]
    ) is True

    assert (
        row[
            "resulting_lifecycle_status"
        ]
        == "active"
    )


def test_missing_source_is_not_deleted() -> None:
    report = build_report(
        [base_prior_row()],
        [],
    )

    row = report.iloc[0]

    assert row["change_type"] == (
        "source_unavailable"
    )

    assert bool(
        row["review_required"]
    ) is False

    assert (
        row[
            "resulting_lifecycle_status"
        ]
        == "active"
    )

    assert (
        row[
            "resulting_source_availability"
        ]
        == "unavailable"
    )


def test_name_change_is_non_identity_change() -> None:
    current = base_current_row()

    current[
        "canonical_product_name"
    ] = "Renamed Booster Box"

    report = build_report(
        [base_prior_row()],
        [current],
    )

    row = report.iloc[0]

    assert row["change_type"] == (
        "source_name_changed"
    )

    assert bool(
        row["review_required"]
    ) is False

    assert row["change_reason"] == (
        "name_changed"
    )


def test_type_change_is_classification_change() -> None:
    current = base_current_row()

    current[
        "canonical_product_type"
    ] = "collector_booster_display"

    report = build_report(
        [base_prior_row()],
        [current],
    )

    row = report.iloc[0]

    assert row["change_type"] == (
        "classification_changed"
    )

    assert bool(
        row["review_required"]
    ) is False

    assert row["change_reason"] == (
        "type_changed"
    )


def test_class_change_is_identity_conflict() -> None:
    current = base_current_row()

    current[
        "canonical_product_class"
    ] = "secret_lair_product"

    report = build_report(
        [base_prior_row()],
        [current],
    )

    row = report.iloc[0]

    assert row["change_type"] == (
        "identity_conflict"
    )

    assert bool(
        row["review_required"]
    ) is True

    assert (
        row[
            "resulting_lifecycle_status"
        ]
        == "identity_review_required"
    )


def test_tcgplayer_change_is_identity_conflict() -> None:
    current = base_current_row()

    current[
        "tcgplayer_product_id"
    ] = "999"

    report = build_report(
        [base_prior_row()],
        [current],
    )

    row = report.iloc[0]

    assert row["change_type"] == (
        "identity_conflict"
    )

    assert bool(
        row["review_required"]
    ) is True

    assert row["change_reason"] == (
        "tcgplayer_id_changed"
    )


def test_duplicate_identity_is_rejected() -> None:
    module = load_module()

    rows = [
        base_prior_row(),
        base_prior_row(),
    ]

    frame = pd.DataFrame(rows)

    try:
        module.build_index(
            frame,
            "canonical_product_id",
            "Test registry",
        )
    except RuntimeError as exc:
        assert "duplicate" in str(
            exc
        ).lower()
    else:
        raise AssertionError(
            "Duplicate identity was accepted."
        )


def test_refresh_does_not_mutate_platforms() -> None:
    summary = json.loads(
        SUMMARY_PATH.read_text(
            encoding="utf-8"
        )
    )

    assert (
        summary[
            "silent_deletions_applied"
        ]
        is False
    )

    assert (
        summary[
            "canonical_registry_changed"
        ]
        is False
    )

    assert (
        summary[
            "production_registry_changed"
        ]
        is False
    )

    assert (
        summary[
            "universal_database_changed"
        ]
        is False
    )