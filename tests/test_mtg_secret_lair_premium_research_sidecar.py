from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT
    / "docs"
    / "phase_8"
    / "secret_lair"
    / "secret_lair_v1_purchase_analysis.csv"
)

EXISTING_EXPORT = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "mtg_v1_uip_export_payload.csv"
)

BUILDER = (
    ROOT
    / "scripts"
    / "build_mtg_secret_lair_premium_research_sidecar.py"
)

OUTPUT = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "premium_research"
    / "mtg_secret_lair_premium_research.csv"
)

SUMMARY = (
    ROOT
    / "docs"
    / "phase_9"
    / "uip_export"
    / "premium_research"
    / "mtg_secret_lair_premium_research_summary.json"
)

EXPECTED_SOURCE_SHA = (
    "eb5efced959116eb7b174d4aff27c06d"
    "321e774eda39b3f8572d958499441cdb"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def read_csv(
    path: Path,
) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        return (
            list(reader),
            list(reader.fieldnames or []),
        )


def test_certified_source_authority_is_exact() -> None:
    rows, fields = read_csv(SOURCE)

    assert sha256(SOURCE) == EXPECTED_SOURCE_SHA
    assert len(rows) == 787
    assert len(fields) == 58

    ids = [
        row["secret_lair_id"].strip()
        for row in rows
    ]

    assert all(ids)
    assert len(set(ids)) == 787


def test_builder_runs_without_mutating_existing_export() -> None:
    before = sha256(EXISTING_EXPORT)

    subprocess.run(
        [
            sys.executable,
            str(BUILDER),
        ],
        cwd=ROOT,
        check=True,
    )

    after = sha256(EXISTING_EXPORT)

    assert before == after


def test_sidecar_population_and_identity_are_exact() -> None:
    rows, fields = read_csv(OUTPUT)

    assert len(rows) == 787
    assert len(fields) == 36

    secret_ids = [
        row["secret_lair_id"]
        for row in rows
    ]

    asset_ids = [
        row["mtg_asset_id"]
        for row in rows
    ]

    assert len(set(secret_ids)) == 787
    assert len(set(asset_ids)) == 787

    assert all(
        asset_id
        == f"SECRET_LAIR_V1_1|{secret_id}"
        for asset_id, secret_id
        in zip(asset_ids, secret_ids)
    )


def test_sidecar_values_are_lossless_source_copies() -> None:
    source_rows, _ = read_csv(SOURCE)
    output_rows, output_fields = read_csv(OUTPUT)

    source_by_id = {
        row["secret_lair_id"].strip(): row
        for row in source_rows
    }

    output_by_id = {
        row["secret_lair_id"].strip(): row
        for row in output_rows
    }

    excluded = {
        "mtg_asset_id",
        "secret_lair_id",
        "source_authority_path",
        "source_authority_sha256",
    }

    copied_fields = [
        field
        for field in output_fields
        if field not in excluded
    ]

    for secret_lair_id, output in output_by_id.items():
        source = source_by_id[secret_lair_id]

        for field in copied_fields:
            assert output[field] == source[field]


def test_lineage_is_exact_on_every_row() -> None:
    rows, _ = read_csv(OUTPUT)

    for row in rows:
        assert (
            row["source_authority_path"]
            == (
                "docs/phase_8/secret_lair/"
                "secret_lair_v1_purchase_analysis.csv"
            )
        )

        assert (
            row["source_authority_sha256"]
            == EXPECTED_SOURCE_SHA
        )


def test_summary_preserves_governance_boundaries() -> None:
    summary = json.loads(
        SUMMARY.read_text(
            encoding="utf-8",
        )
    )

    assert summary["row_count"] == 787
    assert summary["field_count"] == 36

    assert (
        summary["unique_secret_lair_id_count"]
        == 787
    )

    assert (
        summary["unique_mtg_asset_id_count"]
        == 787
    )

    assert (
        summary["one_year_semantic"]
        == "CERTIFIED_FORECAST_AND_EMPIRICAL_RISK"
    )

    assert (
        summary["three_year_semantic"]
        == "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED"
    )

    assert (
        summary["five_year_semantic"]
        == "SCENARIO_DISTRIBUTION_NOT_DIRECTLY_VALIDATED"
    )

    assert (
        summary[
            "q10_is_governed_purchase_entry_threshold"
        ]
        is True
    )

    assert (
        summary[
            "automatic_purchase_execution_authorized"
        ]
        is False
    )

    assert summary["source_values_recomputed"] is False
    assert summary["source_values_synthesized"] is False

    assert (
        summary["existing_23_field_export_modified"]
        is False
    )

    assert summary["uip_ingestion_authorized"] is False
    assert summary["database_write_authorized"] is False
    assert summary["hosted_activation_authorized"] is False
    assert summary["frontend_change_authorized"] is False
