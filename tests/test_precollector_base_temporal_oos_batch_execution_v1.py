import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_base_temporal_oos_batch_execution_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_batch_is_execution_only():
    contract = load()

    assert (
        contract[
            "batching_is_methodological_change"
        ]
        is False
    )

    assert (
        contract[
            "frozen_model_specification_preserved"
        ]
        is True
    )

    assert (
        contract[
            "frozen_hyperparameters_preserved"
        ]
        is True
    )


def test_first_batch_models():
    batch = load()[
        "current_batch"
    ]

    assert batch[
        "batch_id"
    ] == "15W-A"

    assert batch[
        "model_families"
    ] == [
        "LAST_VALUE",
        "DRIFT",
        "LOG_DRIFT",
        "ROBUST_TREND",
        "EXPONENTIAL_SMOOTHING",
    ]

    assert batch[
        "semantic_model_horizon_count"
    ] == 15

    assert batch[
        "governed_matrix_cell_count"
    ] == 180


def test_semantic_duplicates_are_not_independent_models():
    governance = load()[
        "semantic_duplicate_governance"
    ]

    assert (
        governance[
            "semantic_predictions_are_stored_once"
        ]
        is True
    )

    assert (
        governance[
            "duplicate_matrix_cells_count_as_independent_winners"
        ]
        is False
    )


def test_future_execution_remains_blocked():
    auth = load()[
        "authorization"
    ]

    assert (
        auth[
            "current_batch_execution"
        ]
        is True
    )

    assert (
        auth[
            "later_batch_execution"
        ]
        is False
    )

    assert (
        auth[
            "base_tournament_final_certification"
        ]
        is False
    )

    assert (
        auth[
            "ensemble_execution"
        ]
        is False
    )

    assert (
        auth[
            "product_holdout_execution"
        ]
        is False
    )

    assert (
        auth[
            "persistent_exclusion"
        ]
        is False
    )

    assert (
        auth[
            "production_model_selection"
        ]
        is False
    )

    assert (
        auth[
            "monte_carlo_execution"
        ]
        is False
    )

    assert (
        auth[
            "forecast_execution"
        ]
        is False
    )

    assert (
        auth[
            "ranking_execution"
        ]
        is False
    )

    assert (
        auth[
            "purchase_analysis"
        ]
        is False
    )