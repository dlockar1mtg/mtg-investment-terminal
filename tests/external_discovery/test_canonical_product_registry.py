from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

CANONICAL_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "canonical_registry"
    / "canonical_mtg_product_registry_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "canonical_registry"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "canonical_registry_summary_2026-07-22.json"
)

NEW_PRODUCTS_PATH = (
    VALIDATION_ROOT
    / "canonical_registry_new_products_2026-07-22.csv"
)

IDENTITY_REVIEW_PATH = (
    VALIDATION_ROOT
    / "canonical_registry_identity_review_queue_2026-07-22.csv"
)

PRODUCTION_REGISTRY_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

REQUIRED_CANONICAL_COLUMNS = {
    "canonical_product_id",
    "canonical_registry_version",
    "canonical_identity_status",
    "canonical_set_name",
    "canonical_product_name",
    "canonical_product_class",
    "canonical_product_family",
    "canonical_product_type",
    "canonical_packaging_level",
    "language",
    "foil_variant",
    "edition_variant",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "candidate_record_id",
    "source_system",
    "registry_relationship",
    "reconciliation_status",
    "type_alignment",
    "existing_investment_product_id",
    "existing_product_type",
    "existing_approval_status",
    "existing_approval_method",
    "identity_review_status",
    "investment_eligibility_status",
    "investment_approval_status",
    "scoring_status",
    "source_lineage",
}


def load_canonical() -> pd.DataFrame:
    return pd.read_csv(
        CANONICAL_PATH,
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


def test_canonical_registry_totals() -> None:
    canonical = load_canonical()
    summary = load_summary()

    assert len(canonical) == 5239

    assert (
        summary["canonical_registry_rows"]
        == 5239
    )

    assert (
        summary[
            "unique_canonical_product_ids"
        ]
        == 5239
    )

    assert (
        summary[
            "unique_tcgplayer_product_ids"
        ]
        == 5239
    )


def test_canonical_schema_is_complete() -> None:
    canonical = load_canonical()

    assert REQUIRED_CANONICAL_COLUMNS.issubset(
        canonical.columns
    )

    assert canonical[
        "canonical_product_id"
    ].ne("").all()

    assert canonical[
        "candidate_record_id"
    ].ne("").all()

    assert canonical[
        "tcgplayer_product_id"
    ].ne("").all()


def test_canonical_identifiers_are_unique() -> None:
    canonical = load_canonical()

    assert not canonical[
        "canonical_product_id"
    ].duplicated().any()

    assert not canonical[
        "tcgplayer_product_id"
    ].duplicated().any()

    assert not canonical[
        "candidate_record_id"
    ].duplicated().any()


def test_identity_status_breakdown() -> None:
    canonical = load_canonical()

    counts = (
        canonical[
            "canonical_identity_status"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "established_existing_identity": 4674,
        "new_source_identity": 565,
    }


def test_secret_lair_universe_is_preserved() -> None:
    canonical = load_canonical()

    secret_lair = canonical[
        canonical[
            "canonical_product_class"
        ].eq("secret_lair_product")
    ]

    assert len(secret_lair) == 4347

    counts = (
        secret_lair[
            "canonical_identity_status"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "established_existing_identity": 4326,
        "new_source_identity": 21,
    }


def test_new_products_are_not_auto_approved() -> None:
    new_products = pd.read_csv(
        NEW_PRODUCTS_PATH,
        low_memory=False,
        dtype=str,
        keep_default_na=False,
    )

    assert len(new_products) == 565

    assert new_products[
        "investment_approval_status"
    ].eq("review_required").all()

    assert new_products[
        "investment_eligibility_status"
    ].eq("not_evaluated").all()

    assert new_products[
        "scoring_status"
    ].eq("not_scored").all()


def test_existing_approval_information_is_preserved() -> None:
    canonical = load_canonical()

    existing = canonical[
        canonical[
            "canonical_identity_status"
        ].eq(
            "established_existing_identity"
        )
    ]

    counts = (
        existing[
            "existing_approval_status"
        ]
        .value_counts()
        .to_dict()
    )

    assert counts == {
        "review_required": 4440,
        "approved": 234,
    }


def test_case_packaging_is_preserved() -> None:
    canonical = load_canonical()

    cases = canonical[
        canonical[
            "type_alignment"
        ].eq(
            "compatible_registry_generic_"
            "case_packaging"
        )
    ]

    assert len(cases) == 90

    assert cases[
        "canonical_packaging_level"
    ].eq("case").all()

    assert cases[
        "reconciliation_status"
    ].eq("exact_id_match").all()


def test_source_lineage_is_valid_json() -> None:
    canonical = load_canonical()

    for value in canonical[
        "source_lineage"
    ]:
        lineage = json.loads(value)

        assert (
            lineage[
                "candidate_record_id"
            ]
        )

        assert (
            lineage[
                "tcgplayer_product_id"
            ]
        )

        assert lineage[
            "reconciliation_status"
        ] in {
            "exact_id_match",
            "new_candidate",
        }


def test_no_identity_review_or_platform_mutation() -> None:
    review = pd.read_csv(
        IDENTITY_REVIEW_PATH,
        low_memory=False,
    )

    summary = load_summary()

    assert review.empty
    assert summary["identity_review_rows"] == 0

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

    production = pd.read_csv(
        PRODUCTION_REGISTRY_PATH,
        low_memory=False,
    )

    assert len(production) >= 4675

    assert production[
        "investment_product_id"
    ].astype(str).str.strip().is_unique