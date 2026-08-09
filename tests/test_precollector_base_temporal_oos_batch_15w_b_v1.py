import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_base_temporal_oos_batch_15w_b_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_batch_identity():
    contract = load()

    assert contract[
        "batch_id"
    ] == "15W-B"

    assert contract[
        "model_families"
    ] == [
        "RIDGE_REGRESSION",
        "HUBER_REGRESSION",
    ]

    assert contract[
        "governed_matrix_cells"
    ] == 72


def test_temporal_rule():
    rule = load()[
        "temporal_training_rule"
    ]

    assert (
        rule[
            "realized_endpoint_must_be_on_or_before_validation_origin"
        ]
        is True
    )

    assert (
        rule[
            "same_product_prior_matured_examples_allowed"
        ]
        is True
    )

    assert (
        rule[
            "future_or_unmatured_examples_allowed"
        ]
        is False
    )

    assert (
        rule[
            "current_market_features_allowed_historically"
        ]
        is False
    )

    assert (
        rule[
            "random_time_split_allowed"
        ]
        is False
    )


def test_frozen_parameters():
    parameters = load()[
        "model_parameters"
    ]

    assert parameters[
        "RIDGE_REGRESSION"
    ][
        "alpha"
    ] == 1.0

    assert parameters[
        "HUBER_REGRESSION"
    ][
        "epsilon"
    ] == 1.35

    assert parameters[
        "HUBER_REGRESSION"
    ][
        "alpha"
    ] == 0.0001

    assert parameters[
        "HUBER_REGRESSION"
    ][
        "max_iter"
    ] == 1000


def test_downstream_is_blocked():
    auth = load()[
        "authorization"
    ]

    assert auth[
        "current_batch_execution"
    ] is True

    assert auth[
        "later_batch_execution"
    ] is False

    assert auth[
        "ensemble_execution"
    ] is False

    assert auth[
        "product_holdout_execution"
    ] is False

    assert auth[
        "persistent_exclusion"
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