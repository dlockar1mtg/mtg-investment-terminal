import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_finish_base_temporal_oos_tournament_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_tree_models_and_frozen_parameters():

    contract = load()

    tree = contract[
        "tree_batch"
    ]

    assert tree[
        "model_families"
    ] == [
        "RANDOM_FOREST",
        "GRADIENT_BOOSTING",
    ]

    assert tree[
        "governed_matrix_cells"
    ] == 72

    assert tree[
        "random_forest"
    ][
        "n_estimators"
    ] == 500

    assert tree[
        "random_forest"
    ][
        "random_state"
    ] == 20260809

    assert tree[
        "gradient_boosting"
    ][
        "n_estimators"
    ] == 250

    assert tree[
        "gradient_boosting"
    ][
        "random_state"
    ] == 20260809


def test_tree_run_is_resumable():

    tree = load()[
        "tree_batch"
    ]

    assert tree[
        "checkpoint_resume_required"
    ] is True

    assert (
        tree[
            "checkpoint_grain"
        ]
        == "MODEL_X_HORIZON_X_ORIGIN_X_FEATURE_X_TARGET"
    )


def test_temporal_governance():

    temporal = load()[
        "temporal_governance"
    ]

    assert temporal[
        "endpoint_must_be_matured_by_validation_origin"
    ] is True

    assert temporal[
        "same_product_prior_matured_examples_allowed"
    ] is True

    assert temporal[
        "future_or_unmatured_examples_allowed"
    ] is False

    assert temporal[
        "current_market_features_allowed_historically"
    ] is False

    assert temporal[
        "random_time_split_allowed"
    ] is False


def test_full_base_reconciliation_is_396_cells():

    reconciliation = load()[
        "reconciliation"
    ]

    assert reconciliation[
        "total_base_model_families"
    ] == 11

    assert reconciliation[
        "total_governed_base_cells"
    ] == 396

    assert reconciliation[
        "common_fold_paired_comparison_required"
    ] is True

    assert reconciliation[
        "differing_coverage_may_determine_winner"
    ] is False


def test_no_winner_or_exclusion_in_this_step():

    auth = load()[
        "authorization"
    ]

    assert auth[
        "tree_execution"
    ] is True

    assert auth[
        "base_tournament_reconciliation"
    ] is True

    assert auth[
        "certified_base_winner_selection"
    ] is False

    assert auth[
        "persistent_treatment_assignment"
    ] is False

    assert auth[
        "persistent_exclusion"
    ] is False


def test_downstream_execution_remains_blocked():

    auth = load()[
        "authorization"
    ]

    assert auth[
        "ensemble_execution"
    ] is False

    assert auth[
        "product_holdout_execution"
    ] is False

    assert auth[
        "influence_execution"
    ] is False

    assert auth[
        "exclusion_sensitivity_execution"
    ] is False

    assert auth[
        "production_model_selection"
    ] is False

    assert auth[
        "monte_carlo_execution"
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

    assert auth[
        "purchase_recommendations"
    ] is False