from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

POLICY_PATH = (
    ROOT
    / "config"
    / "canonical_registry_governance.yaml"
)

GOVERNED_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry_governance"
    / "governed_canonical_mtg_registry_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "canonical_registry_governance"
)

REVIEW_PATH = (
    VALIDATION_ROOT
    / "canonical_governance_review_queue_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "canonical_governance_summary_2026-07-22.json"
)

CANONICAL_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry"
    / "canonical_mtg_product_registry_2026-07-22.csv"
)

PRODUCTION_REGISTRY_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)


def load_governed() -> pd.DataFrame:
    return pd.read_csv(
        GOVERNED_PATH,
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


def test_governance_policy_is_valid() -> None:
    policy = yaml.safe_load(
        POLICY_PATH.read_text(
            encoding="utf-8"
        )
    )

    assert (
        policy["schema_version"]
        == "10.5R.1C.2.1"
    )

    assert (
        policy["platform_id"]
        == "mtg-investment-terminal"
    )

    assert (
        policy[
            "supersession_rules"
        ][
            "silent_deletion_allowed"
        ]
        is False
    )


def test_governed_registry_totals() -> None:
    governed = load_governed()
    summary = load_summary()

    assert len(governed) == 5239

    assert (
        governed[
            "canonical_product_id"
        ].nunique()
        == 5239
    )

    assert (
        summary[
            "governed_registry_rows"
        ]
        == 5239
    )

    assert (
        summary[
            "unique_canonical_product_ids"
        ]
        == 5239
    )


def test_all_current_identities_are_active() -> None:
    governed = load_governed()

    assert governed[
        "identity_lifecycle_status"
    ].eq("active").all()

    assert governed[
        "source_availability_status"
    ].eq("available").all()


def test_governance_review_breakdown() -> None:
    governed = load_governed()

    counts = (
        governed[
            "governance_review_status"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "not_required": 4674,
        "required": 565,
    }


def test_review_queue_contains_only_new_identities() -> None:
    review = pd.read_csv(
        REVIEW_PATH,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    assert len(review) == 565

    assert review[
        "registry_relationship"
    ].eq(
        "new_candidate_not_in_registry"
    ).all()

    assert review[
        "governance_review_reason"
    ].eq(
        "new_source_identity"
    ).all()

    assert review[
        "investment_approval_status"
    ].eq("review_required").all()


def test_all_products_are_identity_ready() -> None:
    governed = load_governed()
    summary = load_summary()

    assert governed[
        "universal_export_status"
    ].eq("identity_ready").all()

    assert governed[
        "universal_export_block_reason"
    ].eq("").all()

    assert (
        summary[
            "universal_identity_ready_rows"
        ]
        == 5239
    )


def test_identity_readiness_does_not_imply_approval() -> None:
    governed = load_governed()

    counts = (
        governed.groupby(
            [
                "investment_approval_status",
                "governance_review_status",
                "universal_export_status",
            ]
        )
        .size()
        .to_dict()
    )

    assert counts == {
        (
            "approved",
            "not_required",
            "identity_ready",
        ): 234,
        (
            "review_required",
            "not_required",
            "identity_ready",
        ): 4440,
        (
            "review_required",
            "required",
            "identity_ready",
        ): 565,
    }


def test_governance_preserves_canonical_identity() -> None:
    canonical = pd.read_csv(
        CANONICAL_PATH,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    governed = load_governed()

    assert set(
        canonical[
            "canonical_product_id"
        ]
    ) == set(
        governed[
            "canonical_product_id"
        ]
    )

    assert set(
        canonical[
            "tcgplayer_product_id"
        ]
    ) == set(
        governed[
            "tcgplayer_product_id"
        ]
    )


def test_governance_does_not_mutate_platform() -> None:
    summary = load_summary()

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
        summary["database_changed"]
        is False
    )

    assert (
        summary[
            "eligibility_recalculated"
        ]
        is False
    )

    assert (
        summary["scoring_applied"]
        is False
    )

    assert (
        summary[
            "recommendations_created"
        ]
        is False
    )

    assert (
        summary[
            "universal_package_created"
        ]
        is False
    )

    production = pd.read_csv(
        PRODUCTION_REGISTRY_PATH,
        low_memory=False,
    )

    assert len(production) == 4675