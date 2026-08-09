import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AMENDMENT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_base_oos_validation_protocol_amendment_v1.json"
)

ORIGINAL = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_base_oos_model_specification_v1.json"
)


def load(path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def test_amendment_and_original_exist():
    assert AMENDMENT.is_file()
    assert ORIGINAL.is_file()


def test_temporal_oos_allows_only_matured_same_product_history():
    amendment = load(AMENDMENT)

    protocol = amendment[
        "temporal_oos_protocol"
    ]

    assert (
        protocol[
            "same_product_prior_matured_examples_allowed"
        ]
        is True
    )

    assert (
        protocol[
            "same_product_future_or_unmatured_examples_allowed"
        ]
        is False
    )

    assert (
        protocol[
            "future_endpoint_information_allowed"
        ]
        is False
    )


def test_product_holdout_remains_required_separately():
    amendment = load(AMENDMENT)

    holdout = amendment[
        "product_holdout_protocol"
    ]

    assert holdout["required"] is True

    assert (
        holdout[
            "all_training_examples_from_held_out_product_excluded"
        ]
        is True
    )

    assert (
        holdout[
            "product_holdout_results_must_be_reported_separately"
        ]
        is True
    )


def test_model_specification_not_changed():
    amendment = load(AMENDMENT)

    effect = amendment[
        "methodological_effect"
    ]

    assert effect[
        "model_families_changed"
    ] is False

    assert effect[
        "hyperparameters_changed"
    ] is False

    assert effect[
        "target_transformations_changed"
    ] is False

    assert effect[
        "feature_variants_changed"
    ] is False

    assert effect[
        "horizons_changed"
    ] is False

    assert effect[
        "theoretical_matrix_changed"
    ] is False

    assert effect[
        "base_matrix_cells_changed"
    ] is False


def test_amendment_is_pre_result():
    amendment = load(AMENDMENT)

    anti = amendment[
        "anti_cherry_picking"
    ]

    assert (
        anti[
            "amendment_occurs_before_first_oos_model_result"
        ]
        is True
    )

    assert anti[
        "hyperparameters_remain_frozen"
    ] is True

    assert anti[
        "product_treatments_assigned"
    ] == 0

    assert anti[
        "product_exclusions_assigned"
    ] == 0


def test_downstream_execution_still_blocked():
    amendment = load(AMENDMENT)

    auth = amendment[
        "authorization"
    ]

    assert (
        auth[
            "direct_temporal_oos_base_execution"
        ]
        is True
    )

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