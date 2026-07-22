from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "source_coverage"
)


def test_source_coverage_outputs_exist() -> None:
    required_files = [
        "repository_file_inventory.csv",
        "candidate_data_source_inventory.csv",
        "database_table_inventory.csv",
        "external_source_reference_inventory.csv",
        "preliminary_source_registry.csv",
        "source_coverage_audit_summary.json",
        "operational_source_file_audit.csv",
        "operational_source_summary.csv",
        "product_registry_coverage.json",
        "database_product_coverage.json",
        "source_coverage_verification.json",
    ]

    for filename in required_files:
        assert (OUTPUT_ROOT / filename).is_file()


def test_registry_coverage_is_reconciled() -> None:
    coverage = json.loads(
        (
            OUTPUT_ROOT
            / "product_registry_coverage.json"
        ).read_text(encoding="utf-8")
    )

    assert coverage["row_count"] == 4675
    assert coverage["approved_count"] == 234
    assert coverage["unapproved_count"] == 4441

    assert (
        coverage["approved_count"]
        + coverage["unapproved_count"]
        == coverage["row_count"]
    )

    assert coverage["unique_investment_product_ids"] == 4675
    assert coverage["unique_tcgplayer_product_ids"] == 4675


def test_registry_contains_expected_product_families() -> None:
    coverage = json.loads(
        (
            OUTPUT_ROOT
            / "product_registry_coverage.json"
        ).read_text(encoding="utf-8")
    )

    counts = coverage["product_type_counts"]

    assert counts["Secret Lair Drop"] == 4327
    assert counts["Traditional Booster Display"] == 210
    assert counts["Collector Booster Display"] == 77
    assert counts["Draft Booster Display"] == 42
    assert counts["Masters Booster Display"] == 19

    assert sum(counts.values()) == 4675


def test_external_coverage_is_not_prematurely_certified() -> None:
    verification = json.loads(
        (
            OUTPUT_ROOT
            / "source_coverage_verification.json"
        ).read_text(encoding="utf-8")
    )

    assert verification["verification_status"] == (
        "OPERATIONAL_SOURCE_REVIEW_COMPLETE"
    )

    assert verification["certification_status"] == (
        "NOT_CERTIFIED_EXTERNAL_COVERAGE_REQUIRED"
    )

    assert verification["next_phase"] == (
        "10.5R.1B External Product Discovery"
    )


def test_operational_source_summary_has_expected_sources() -> None:
    frame = pd.read_csv(
        OUTPUT_ROOT
        / "operational_source_summary.csv"
    )

    statuses = dict(
        zip(
            frame["source_name"],
            frame["provisional_operational_status"],
            strict=True,
        )
    )

    assert statuses["tcgcsv"] == "operational_candidate"
    assert statuses["scryfall"] == "operational_candidate"
    assert statuses["tcgplayer_api"] == "operational_candidate"

    assert statuses["ebay"] == "not_implemented"
    assert statuses["cardmarket"] == "not_implemented"
    assert statuses["card_kingdom"] == "not_implemented"
    assert statuses["star_city_games"] == "not_implemented"
    assert statuses["coolstuffinc"] == "not_implemented"