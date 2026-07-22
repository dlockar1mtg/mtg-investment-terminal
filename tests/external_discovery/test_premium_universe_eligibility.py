from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_PATH = (
    ROOT
    / "scripts"
    / "external_discovery"
    / "audit_premium_universe_eligibility.py"
)

POLICY_PATH = (
    ROOT
    / "config"
    / "premium_mtg_eligibility.yaml"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "premium_universe_eligibility"
)

AUDIT_PATH = (
    OUTPUT_ROOT
    / "premium_universe_eligibility_audit_2026-07-22.csv"
)

SUMMARY_PATH = (
    OUTPUT_ROOT
    / "premium_universe_eligibility_summary_2026-07-22.json"
)

SECRET_LAIR_PATH = (
    OUTPUT_ROOT
    / "secret_lair_structural_candidates_2026-07-22.csv"
)

HISTORICAL_PATH = (
    OUTPUT_ROOT
    / "historical_booster_review_2026-07-22.csv"
)

CLASSIFICATION_PATH = (
    OUTPUT_ROOT
    / "sealed_product_classification_review_2026-07-22.csv"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "premium_eligibility",
        SCRIPT_PATH,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(module)

    return module


def make_row(
    *,
    product_class: str = "sealed_product",
    product_type: str = "collector_booster_display",
    packaging_level: str = "display",
    product_name: str = "Example Product",
) -> pd.Series:
    return pd.Series(
        {
            "canonical_product_id": (
                "MTG-CANON-TCGPLAYER-100"
            ),
            "tcgplayer_product_id": "100",
            "canonical_product_name": (
                product_name
            ),
            "canonical_product_class": (
                product_class
            ),
            "canonical_product_family": (
                "booster_display"
            ),
            "canonical_product_type": (
                product_type
            ),
            "canonical_packaging_level": (
                packaging_level
            ),
            "identity_lifecycle_status": (
                "active"
            ),
            "source_availability_status": (
                "available"
            ),
            "governance_review_status": (
                "approved"
            ),
            "universal_export_status": (
                "identity_ready"
            ),
        }
    )


def test_policy_matches_approved_strategy() -> None:
    policy = yaml.safe_load(
        POLICY_PATH.read_text(
            encoding="utf-8"
        )
    )

    assert (
        policy["case_policy"]["include_cases"]
        is False
    )

    secret_lair = policy[
        "secret_lair_policy"
    ]

    assert (
        secret_lair[
            "sealed_single_card_drop_allowed"
        ]
        is True
    )

    assert (
        secret_lair[
            "sealed_multi_card_drop_allowed"
        ]
        is True
    )

    assert (
        secret_lair[
            "opened_individual_card_allowed"
        ]
        is False
    )


def test_collector_display_is_candidate() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row()
    )

    assert state == "structurally_eligible"
    assert reason == "collector_booster_display"


def test_case_is_excluded() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            packaging_level="case",
            product_name=(
                "Example Collector Booster Case"
            ),
        )
    )

    assert state == "structurally_ineligible"
    assert reason == "case_level_product_excluded"


def test_secret_lair_bundle_is_candidate() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_class="secret_lair_product",
            product_type=(
                "secret_lair_bundle_or_kit"
            ),
            packaging_level="bundle",
            product_name="Example Secret Lair Bundle",
        )
    )

    assert state == "structurally_eligible"

    assert reason == (
        "sealed_secret_lair_bundle_or_kit"
    )


def test_secret_lair_individual_card_is_excluded() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_class="secret_lair_product",
            product_type=(
                "secret_lair_card_or_product"
            ),
            packaging_level=(
                "individual_card_or_variant"
            ),
            product_name="Example Secret Lair Card",
        )
    )

    assert state == "structurally_ineligible"

    assert reason == (
        "individual_card_from_secret_lair_drop"
    )


def test_secret_lair_variant_is_excluded() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_class="secret_lair_product",
            product_type=(
                "secret_lair_card_variant"
            ),
            packaging_level=(
                "individual_card_or_variant"
            ),
        )
    )

    assert state == "structurally_ineligible"

    assert reason == (
        "separately_listed_secret_lair_card_variant"
    )


def test_secret_lair_insert_is_excluded() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_class="secret_lair_product",
            product_type="secret_lair_insert",
            packaging_level=(
                "individual_card_insert"
            ),
        )
    )

    assert state == "structurally_ineligible"
    assert reason == "secret_lair_insert_excluded"


def test_secret_lair_commander_deck_is_excluded() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_class="secret_lair_product",
            product_type=(
                "secret_lair_card_or_product"
            ),
            packaging_level="deck",
            product_name=(
                "Secret Lair Commander Deck: Example"
            ),
        )
    )

    assert state == "structurally_ineligible"

    assert reason == (
        "secret_lair_commander_deck_excluded"
    )


def test_traditional_booster_requires_review() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_type=(
                "traditional_booster_display"
            )
        )
    )

    assert state == "historical_review_required"

    assert reason == (
        "traditional_booster_display"
        "_requires_premium_history_review"
    )


def test_draft_booster_requires_review() -> None:
    module = load_module()

    state, reason = module.classify_row(
        make_row(
            product_type="draft_booster_display"
        )
    )

    assert state == "historical_review_required"

    assert reason == (
        "draft_booster_display"
        "_requires_premium_history_review"
    )


def test_theme_and_jumpstart_are_excluded() -> None:
    module = load_module()

    for product_type in (
        "theme_booster_display",
        "jumpstart_booster_display",
    ):
        state, reason = module.classify_row(
            make_row(
                product_type=product_type
            )
        )

        assert state == "structurally_ineligible"

        assert reason == (
            f"excluded_product_type:{product_type}"
        )


def test_governance_block_prevents_candidate() -> None:
    module = load_module()

    row = make_row()

    row[
        "source_availability_status"
    ] = "unavailable"

    state, reason = module.classify_row(
        row
    )

    assert state == "structurally_ineligible"
    assert "source_not_available" in reason


def test_baseline_output_counts() -> None:
    summary = json.loads(
        SUMMARY_PATH.read_text(
            encoding="utf-8"
        )
    )

    assert summary["audit_status"] == "PASS"
    assert summary["audit_rows"] == 5239

    assert (
        summary["unique_canonical_product_ids"]
        == 5239
    )

    assert (
        summary["structural_candidate_rows"]
        == 307
    )

    assert (
        summary["structural_exclusion_rows"]
        == 4769
    )

    assert (
        summary["review_queue_rows"]
        == 163
    )

    assert (
        summary["secret_lair_candidate_rows"]
        == 254
    )

    assert (
        summary["historical_review_rows"]
        == 163
    )

    assert (
        summary["classification_review_rows"]
        == 0
    )


def test_baseline_has_no_premature_promotion() -> None:
    audit = pd.read_csv(
        AUDIT_PATH,
        dtype=str,
        keep_default_na=False,
    )

    assert set(
        audit["final_eligibility_decision"]
    ) == {"not_decided"}

    assert set(
        audit["scoring_allowed"]
    ) == {"False"}

    assert set(
        audit["universal_investable_allowed"]
    ) == {"False"}


def test_focused_outputs_match_summary() -> None:
    secret_lair = pd.read_csv(
        SECRET_LAIR_PATH,
        dtype=str,
        keep_default_na=False,
    )

    historical = pd.read_csv(
        HISTORICAL_PATH,
        dtype=str,
        keep_default_na=False,
    )

    classification = pd.read_csv(
        CLASSIFICATION_PATH,
        dtype=str,
        keep_default_na=False,
    )

    assert len(secret_lair) == 254
    assert len(historical) == 163
    assert classification.empty

    assert set(
        historical[
            "canonical_product_type"
        ]
    ) == {
        "traditional_booster_display",
        "draft_booster_display",
    }


def test_safety_controls_remain_false() -> None:
    summary = json.loads(
        SUMMARY_PATH.read_text(
            encoding="utf-8"
        )
    )

    assert (
        summary["canonical_registry_changed"]
        is False
    )

    assert (
        summary["governed_registry_changed"]
        is False
    )

    assert (
        summary["production_registry_changed"]
        is False
    )

    assert (
        summary["eligibility_promoted"]
        is False
    )

    assert summary["scoring_applied"] is False

    assert (
        summary["universal_database_changed"]
        is False
    )