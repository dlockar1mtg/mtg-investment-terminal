import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_large_step_2_ensemble_robustness_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_complete_base_binding():

    contract = load()

    assert contract[
        "complete_base_tournament"
    ][
        "base_model_families"
    ] == 11

    assert contract[
        "complete_base_tournament"
    ][
        "governed_cells"
    ] == 396


def test_nested_ensemble_governance():

    rules = load()[
        "ensemble_rules"
    ]

    assert (
        rules[
            "current_origin_actual_outcomes_may_select_components"
        ]
        is False
    )

    assert (
        rules[
            "only_prior_origin_oos_information_may_select_components"
        ]
        is True
    )

    assert (
        rules[
            "ensemble_component_predictions_must_be_genuine_oos"
        ]
        is True
    )


def test_product_holdout_is_genuine():

    holdout = load()[
        "product_holdout"
    ]

    assert (
        holdout[
            "genuine_refit_required_for_cross_product_pooled_candidate"
        ]
        is True
    )

    assert (
        holdout[
            "posthoc_residual_removal_is_genuine_holdout"
        ]
        is False
    )

    assert (
        holdout[
            "checkpoint_resume_required"
        ]
        is True
    )


def test_no_arbitrary_exclusion_rule():

    governance = load()[
        "product_governance"
    ]

    assert governance[
        "automatic_downweighting"
    ] is False

    assert governance[
        "automatic_exclusion"
    ] is False

    assert governance[
        "high_nominal_price_alone_can_exclude"
    ] is False

    assert governance[
        "release_age_alone_can_exclude"
    ] is False

    assert governance[
        "missing_market_domain_alone_can_exclude"
    ] is False

    assert governance[
        "single_diagnostic_alone_can_exclude"
    ] is False


def test_downstream_stays_blocked():

    auth = load()[
        "authorization"
    ]

    assert auth[
        "ensemble_diagnostics"
    ] is True

    assert auth[
        "robustness_diagnostics"
    ] is True

    assert auth[
        "genuine_product_holdout_diagnostics"
    ] is True

    assert auth[
        "persistent_treatment_assignment"
    ] is False

    assert auth[
        "persistent_exclusion"
    ] is False

    assert auth[
        "final_model_selection"
    ] is False

    assert auth[
        "production_model_execution"
    ] is False

    assert auth[
        "forecast_execution"
    ] is False

    assert auth[
        "monte_carlo_execution"
    ] is False

    assert auth[
        "ranking_execution"
    ] is False

    assert auth[
        "purchase_analysis"
    ] is False