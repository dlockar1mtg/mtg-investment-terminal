from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_REGISTRY = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

BASELINE_REGISTRY = (
    ROOT
    / "data"
    / "governance"
    / "mtg"
    / "collector_booster_admissions"
    / "registry_baseline_v1.csv"
)

BASELINE_MANIFEST = (
    ROOT
    / "data"
    / "governance"
    / "mtg"
    / "collector_booster_admissions"
    / "registry_baseline_manifest.json"
)

ADMISSIONS_LEDGER = (
    ROOT
    / "data"
    / "governance"
    / "mtg"
    / "collector_booster_admissions"
    / "applied_admissions.csv"
)


def clean_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def load_frames() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    production = pd.read_csv(
        PRODUCTION_REGISTRY,
        low_memory=False,
    )
    baseline = pd.read_csv(
        BASELINE_REGISTRY,
        low_memory=False,
    )
    admissions = pd.read_csv(
        ADMISSIONS_LEDGER,
        low_memory=False,
    )

    return production, baseline, admissions


def test_registry_matches_baseline_plus_governed_admissions() -> None:
    production, baseline, admissions = load_frames()

    active = admissions[
        clean_series(admissions["active"]).str.lower()
        == "true"
    ].copy()

    baseline_ids = set(
        clean_series(
            baseline["investment_product_id"]
        )
    )

    admission_ids = set(
        clean_series(
            active["investment_product_id"]
        )
    )

    production_ids = set(
        clean_series(
            production["investment_product_id"]
        )
    )

    expected_ids = baseline_ids | admission_ids

    assert production_ids == expected_ids
    assert len(production) == len(expected_ids)


def test_all_added_products_have_governed_admission() -> None:
    production, baseline, admissions = load_frames()

    baseline_ids = set(
        clean_series(
            baseline["investment_product_id"]
        )
    )

    production_ids = set(
        clean_series(
            production["investment_product_id"]
        )
    )

    added_ids = production_ids - baseline_ids

    active = admissions[
        clean_series(admissions["active"]).str.lower()
        == "true"
    ].copy()

    admitted_ids = set(
        clean_series(
            active["investment_product_id"]
        )
    )

    assert added_ids == admitted_ids


def test_admitted_identity_fields_are_unique() -> None:
    production, _, _ = load_frames()

    investment_ids = clean_series(
        production["investment_product_id"]
    )
    tcgplayer_ids = clean_series(
        production["approved_tcgplayer_product_id"]
    )

    assert investment_ids.ne("").all()
    assert investment_ids.is_unique

    populated_tcgplayer_ids = tcgplayer_ids[
        tcgplayer_ids.ne("")
    ]

    assert populated_tcgplayer_ids.is_unique


def test_governed_admission_metadata_is_valid() -> None:
    production, baseline, admissions = load_frames()

    baseline_ids = set(
        clean_series(
            baseline["investment_product_id"]
        )
    )

    added = production[
        ~clean_series(
            production["investment_product_id"]
        ).isin(baseline_ids)
    ].copy()

    active = admissions[
        clean_series(admissions["active"]).str.lower()
        == "true"
    ].copy()

    assert len(added) == len(active)

    assert (
        clean_series(
            added["approval_method"]
        )
        == "governed_auto_admission_v1"
    ).all()

    assert (
        clean_series(
            active["admission_status"]
        )
        == "AUTO_ADMITTED"
    ).all()

    assert (
        clean_series(
            active["identity_status"]
        )
        == "VERIFIED"
    ).all()

    assert (
        clean_series(
            active["admission_policy_version"]
        )
        == "1.0.0"
    ).all()


def test_baseline_manifest_matches_baseline() -> None:
    baseline = pd.read_csv(
        BASELINE_REGISTRY,
        low_memory=False,
    )

    manifest = json.loads(
        BASELINE_MANIFEST.read_text(
            encoding="utf-8-sig"
        )
    )

    assert manifest["baseline_rows"] == len(baseline)
    assert manifest["baseline_version"] == "1.0.0"