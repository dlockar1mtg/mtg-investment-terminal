import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_empirical_eligibility_diagnostics_v1_contract.json"
)


def load_contract():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_all_ten_required_dimensions_are_preserved():
    contract = load_contract()

    required = set(
        contract[
            "required_diagnostic_dimensions"
        ]
    )

    assert required == {
        "PRICE_HISTORY_COVERAGE",
        "PRICE_HISTORY_STALENESS",
        "PRICE_PATH_STABILITY",
        "CURRENT_AVAILABILITY",
        "LIQUIDITY_OR_MARKET_DEPTH",
        "SOURCE_DISAGREEMENT",
        "STATISTICAL_INFLUENCE",
        "OUT_OF_SAMPLE_ERROR_CONTRIBUTION",
        "MODEL_STABILITY",
        "EXCLUSION_SENSITIVITY",
    }


def test_model_dependent_dimensions_remain_pending():
    contract = load_contract()

    assert set(
        contract[
            "model_dependent_diagnostics_pending"
        ]
    ) == {
        "STATISTICAL_INFLUENCE",
        "OUT_OF_SAMPLE_ERROR_CONTRIBUTION",
        "MODEL_STABILITY",
        "EXCLUSION_SENSITIVITY",
    }


def test_no_arbitrary_cutoffs():
    contract = load_contract()

    governance = contract[
        "eligibility_governance"
    ]

    assert (
        governance[
            "arbitrary_age_cutoff_allowed"
        ]
        is False
    )

    assert (
        governance[
            "arbitrary_history_count_cutoff_allowed"
        ]
        is False
    )

    assert (
        governance[
            "arbitrary_listing_count_cutoff_allowed"
        ]
        is False
    )

    assert (
        governance[
            "arbitrary_seller_count_cutoff_allowed"
        ]
        is False
    )


def test_diagnostics_cannot_exclude_products():
    contract = load_contract()

    governance = contract[
        "eligibility_governance"
    ]

    assert (
        governance[
            "diagnostics_stage_may_exclude_products"
        ]
        is False
    )

    assert (
        governance[
            "canonical_membership_may_be_changed"
        ]
        is False
    )

    assert (
        governance[
            "training_membership_selected_in_this_stage"
        ]
        is False
    )


def test_source_disagreement_does_not_promote_ebay_to_price_authority():
    contract = load_contract()

    disagreement = contract[
        "source_disagreement"
    ]

    assert (
        disagreement[
            "tcgcsv_current_vs_ebay_median"
        ]
        is True
    )

    assert (
        disagreement[
            "no_ebay_price_authority_created"
        ]
        is True
    )


def test_model_execution_remains_disabled():
    contract = load_contract()

    auth = contract[
        "authorization"
    ]

    assert auth["model_execution"] is False
    assert auth["statistical_influence_execution"] is False
    assert auth["out_of_sample_execution"] is False
    assert auth["exclusion_sensitivity_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False