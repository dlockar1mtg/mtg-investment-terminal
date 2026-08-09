import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_model_tournament_and_oos_design_v1.json"
)

EXPECTED_IDENTITY = (
    "d540be20ff26709b8e004e18ff16a11a05f50a1182777dcfd86a1821f62b7ac2"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_contract_bound_to_corrected_131_universe():
    contract = load()

    assert (
        contract[
            "canonical_binding"
        ][
            "product_count"
        ]
        == 131
    )

    assert (
        contract[
            "canonical_binding"
        ][
            "identity_sha256"
        ]
        == EXPECTED_IDENTITY
    )


def test_investment_horizons_are_governed():
    contract = load()

    horizons = contract[
        "forecast_horizons"
    ]

    assert horizons[
        "governed_investment_horizons_days"
    ] == [
        365,
        1095,
        1825,
    ]

    assert (
        horizons[
            "primary_investment_horizon_days"
        ]
        == 1095
    )

    assert (
        horizons[
            "unsupported_horizon_is_product_exclusion"
        ]
        is False
    )


def test_short_horizons_are_diagnostic_only():
    contract = load()

    assert (
        contract[
            "forecast_horizons"
        ][
            "diagnostic_support_days"
        ]
        == [
            90,
            180,
        ]
    )


def test_temporal_anti_leakage_controls_required():
    contract = load()

    validation = contract[
        "validation_design"
    ]

    assert validation[
        "temporal_order_required"
    ] is True

    assert validation[
        "anti_leakage_required"
    ] is True

    assert validation[
        "rolling_origin_required"
    ] is True

    assert validation[
        "no_random_time_shuffling"
    ] is True


def test_product_holdout_is_required():
    contract = load()

    validation = contract[
        "validation_design"
    ]

    assert validation[
        "product_level_holdout_required"
    ] is True

    assert validation[
        "leave_one_product_out_when_computationally_practical"
    ] is True


def test_no_arbitrary_minimum_fold_count():
    contract = load()

    folds = contract[
        "fold_construction"
    ]

    assert (
        folds[
            "minimum_fold_count_predeclared"
        ]
        is False
    )

    assert (
        folds[
            "insufficient_realized_folds_is_product_exclusion"
        ]
        is False
    )


def test_all_four_pending_diagnostics_are_required():
    contract = load()

    diagnostics = contract[
        "required_model_dependent_diagnostics"
    ]

    assert diagnostics[
        "statistical_influence"
    ][
        "required"
    ] is True

    assert diagnostics[
        "out_of_sample_error_contribution"
    ][
        "required"
    ] is True

    assert diagnostics[
        "model_stability"
    ][
        "required"
    ] is True

    assert diagnostics[
        "exclusion_sensitivity"
    ][
        "required"
    ] is True


def test_no_single_metric_exclusion():
    contract = load()

    assert (
        contract[
            "evaluation_metrics"
        ][
            "no_single_metric_may_authorize_persistent_exclusion"
        ]
        is True
    )

    assert (
        contract[
            "required_model_dependent_diagnostics"
        ][
            "exclusion_sensitivity"
        ][
            "persistent_exclusion_cannot_be_justified_by_score_improvement_alone"
        ]
        is True
    )


def test_age_and_liquidity_are_features_not_fixed_exclusions():
    contract = load()

    feature = contract[
        "feature_governance"
    ]

    assert feature[
        "release_age_may_be_predictor"
    ] is True

    assert feature[
        "release_age_may_be_exclusion_rule"
    ] is False

    assert feature[
        "liquidity_may_be_predictor"
    ] is True

    assert feature[
        "liquidity_may_be_fixed_exclusion_threshold"
    ] is False


def test_ebay_is_not_promoted_to_price_authority():
    contract = load()

    feature = contract[
        "feature_governance"
    ]

    assert feature[
        "ebay_price_used_as_target_authority"
    ] is False

    assert feature[
        "tcgcsv_current_price_remains_price_authority"
    ] is True


def test_long_horizon_scenario_labeling_required():
    contract = load()

    long_horizon = contract[
        "long_horizon_governance"
    ]

    assert (
        long_horizon[
            "direct_three_year_backtest_required_to_claim_historical_validation"
        ]
        is True
    )

    assert (
        long_horizon[
            "direct_five_year_backtest_required_to_claim_historical_validation"
        ]
        is True
    )

    assert (
        long_horizon[
            "scenario_must_be_distinguished_from_validated_forecast"
        ]
        is True
    )


def test_no_execution_is_authorized():
    contract = load()

    auth = contract[
        "execution_authorization"
    ]

    assert auth[
        "tournament_design_certification"
    ] is True

    assert auth[
        "tournament_execution"
    ] is False

    assert auth[
        "model_execution"
    ] is False

    assert auth[
        "treatment_assignment"
    ] is False

    assert auth[
        "persistent_exclusion"
    ] is False

    assert auth[
        "forecast_execution"
    ] is False

    assert auth[
        "ranking_execution"
    ] is False

    assert auth[
        "purchase_analysis"
    ] is False