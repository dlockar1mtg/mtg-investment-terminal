import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_availability_authority_v1_contract.json"
)


def load_contract():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_authority_targets_131_products():
    contract = load_contract()

    assert (
        contract["canonical_universe"]["product_count"]
        == 131
    )


def test_semantic_specificity_rule_is_governed():
    contract = load_contract()
    identity = contract["identity_rules"]

    assert (
        identity[
            "generic_identity_loses_to_explicit_more_specific_identity"
        ]
        is True
    )

    assert (
        identity[
            "semantic_rule_empirically_tested_collision_count"
        ]
        == 94
    )

    assert (
        identity[
            "semantic_rule_resolved_collision_count"
        ]
        == 89
    )

    assert (
        identity[
            "residual_unresolved_collision_count"
        ]
        == 5
    )

    assert (
        identity[
            "residual_collisions_admitted"
        ]
        is False
    )


def test_explicit_sealed_metadata_rule_is_narrow():
    contract = load_contract()
    seals = contract["sealed_evidence_rules"]

    assert (
        seals[
            "explicit_condition_metadata_accepted"
        ]
        is True
    )

    assert (
        seals[
            "explicit_condition_metadata_requires_full_identity_token_coverage"
        ]
        is True
    )

    assert (
        seals[
            "explicit_condition_metadata_requires_valid_box_or_display_form"
        ]
        is True
    )

    assert (
        seals[
            "plain_new_accepted_as_sealed"
        ]
        is False
    )

    assert (
        seals[
            "used_accepted_as_sealed"
        ]
        is False
    )


def test_expected_partial_coverage():
    contract = load_contract()
    coverage = contract["coverage"]

    assert (
        coverage[
            "certified_availability_products"
        ]
        == 111
    )

    assert (
        coverage[
            "explicit_availability_gap_products"
        ]
        == 20
    )

    assert (
        coverage[
            "complete_coverage_required"
        ]
        is False
    )


def test_no_arbitrary_liquidity_thresholds():
    contract = load_contract()
    liquidity = contract[
        "liquidity_governance"
    ]

    assert (
        liquidity[
            "minimum_listing_count_threshold_used"
        ]
        is False
    )

    assert (
        liquidity[
            "minimum_seller_count_threshold_used"
        ]
        is False
    )

    assert (
        liquidity[
            "listing_count_is_empirical_feature"
        ]
        is True
    )


def test_gap_does_not_auto_exclude():
    contract = load_contract()
    coverage = contract["coverage"]

    assert (
        coverage[
            "availability_gap_implies_model_exclusion"
        ]
        is False
    )

    assert (
        coverage[
            "availability_gap_implies_prediction_exclusion"
        ]
        is False
    )


def test_model_execution_remains_disabled():
    contract = load_contract()
    auth = contract["authorization"]

    assert (
        auth["empirical_model_eligibility_diagnostics"]
        is True
    )

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False