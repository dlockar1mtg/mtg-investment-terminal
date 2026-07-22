from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

ASSET_MASTER_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "universal_mapping"
    / "asset_master_preview_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "universal_mapping"
)

IDENTITY_MAP_PATH = (
    VALIDATION_ROOT
    / "canonical_to_universal_identity_map_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "asset_master_mapping_summary_2026-07-22.json"
)

VALIDATION_PATH = (
    VALIDATION_ROOT
    / "asset_master_mapping_validation_2026-07-22.json"
)

GOVERNED_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
    / "governed_canonical_mtg_registry_2026-07-22.csv"
)

EXPECTED_COLUMNS = [
    "contract_version",
    "platform_id",
    "run_id",
    "universal_asset_id",
    "platform_asset_id",
    "asset_name",
    "asset_symbol",
    "asset_class",
    "asset_subclass",
    "currency",
    "market_or_region",
    "is_active",
    "investable",
    "liquidity_tier",
    "data_source",
    "first_available_date",
    "last_updated_at_utc",
]


def load_asset_master() -> pd.DataFrame:
    return pd.read_csv(
        ASSET_MASTER_PATH,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )


def load_summary() -> dict[str, object]:
    return json.loads(
        SUMMARY_PATH.read_text(
            encoding="utf-8"
        )
    )


def test_asset_master_contract_columns() -> None:
    asset_master = load_asset_master()

    assert list(asset_master.columns) == (
        EXPECTED_COLUMNS
    )


def test_asset_master_row_and_identity_counts() -> None:
    asset_master = load_asset_master()
    summary = load_summary()

    assert len(asset_master) == 5239

    assert (
        asset_master[
            "universal_asset_id"
        ].nunique()
        == 5239
    )

    assert (
        asset_master[
            "platform_asset_id"
        ].nunique()
        == 5239
    )

    assert (
        summary["asset_master_rows"]
        == 5239
    )


def test_required_contract_fields_are_populated() -> None:
    asset_master = load_asset_master()

    required = [
        "contract_version",
        "platform_id",
        "run_id",
        "universal_asset_id",
        "platform_asset_id",
        "asset_name",
        "asset_class",
        "is_active",
        "investable",
        "last_updated_at_utc",
    ]

    for column in required:
        assert asset_master[
            column
        ].ne("").all()


def test_contract_and_platform_identity() -> None:
    asset_master = load_asset_master()

    assert asset_master[
        "contract_version"
    ].eq("1.0.0").all()

    assert asset_master[
        "platform_id"
    ].eq("mtg").all()

    assert asset_master[
        "run_id"
    ].eq(
        "mtg-canonical-asset-master-"
        "preview-20260722"
    ).all()


def test_universal_identifiers_are_deterministic() -> None:
    asset_master = load_asset_master()

    canonical_pattern = re.compile(
        r"^MTG-CANON-TCGPLAYER-(\d+)$"
    )

    universal_pattern = re.compile(
        r"^mtg:tcgplayer:(\d+)$"
    )

    for row in asset_master.itertuples(
        index=False
    ):
        canonical_match = (
            canonical_pattern.fullmatch(
                row.platform_asset_id
            )
        )

        universal_match = (
            universal_pattern.fullmatch(
                row.universal_asset_id
            )
        )

        assert canonical_match is not None
        assert universal_match is not None

        assert (
            canonical_match.group(1)
            == universal_match.group(1)
        )


def test_asset_class_and_subclasses() -> None:
    asset_master = load_asset_master()

    assert asset_master[
        "asset_class"
    ].eq("collectible").all()

    counts = (
        asset_master[
            "asset_subclass"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "mtg_secret_lair_product": 4347,
        "mtg_sealed_product": 892,
    }


def test_all_current_identities_are_active() -> None:
    asset_master = load_asset_master()

    assert asset_master[
        "is_active"
    ].eq("True").all()


def test_no_identity_is_prematurely_investable() -> None:
    asset_master = load_asset_master()
    governed = pd.read_csv(
        GOVERNED_PATH,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    assert asset_master[
        "investable"
    ].eq("False").all()

    assert governed[
        "investment_eligibility_status"
    ].eq("not_evaluated").all()


def test_identity_map_matches_asset_master() -> None:
    asset_master = load_asset_master()

    identity_map = pd.read_csv(
        IDENTITY_MAP_PATH,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    assert len(identity_map) == 5239

    expected = asset_master[
        [
            "universal_asset_id",
            "platform_asset_id",
            "asset_name",
            "asset_class",
            "asset_subclass",
            "is_active",
            "investable",
        ]
    ].reset_index(drop=True)

    pd.testing.assert_frame_equal(
        identity_map.reset_index(
            drop=True
        ),
        expected,
        check_dtype=False,
    )


def test_mapping_validation_reports_pass() -> None:
    validation = json.loads(
        VALIDATION_PATH.read_text(
            encoding="utf-8"
        )
    )

    summary = load_summary()

    assert (
        validation[
            "validation_status"
        ]
        == "PASS"
    )

    assert validation["errors"] == []

    assert (
        validation[
            "actual_column_count"
        ]
        == 17
    )

    assert validation["row_count"] == 5239

    assert (
        summary["mapping_status"]
        == "PASS"
    )

    assert (
        summary["validation_errors"]
        == []
    )


def test_mapping_does_not_mutate_platforms() -> None:
    summary = load_summary()

    assert (
        summary[
            "universal_package_created"
        ]
        is False
    )

    assert (
        summary[
            "universal_database_changed"
        ]
        is False
    )

    assert (
        summary[
            "mtg_production_registry_changed"
        ]
        is False
    )