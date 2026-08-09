import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_base_oos_model_specification_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_base_and_ensemble_partition():
    spec = load()["execution_accounting"]

    assert spec["base_family_count"] == 11
    assert spec["deferred_ensemble_family_count"] == 2
    assert spec["base_matrix_cells"] == 396
    assert spec["deferred_ensemble_cells"] == 72

    assert (
        spec["base_matrix_cells"]
        + spec["deferred_ensemble_cells"]
        == spec["theoretical_direct_oos_cells"]
        == 468
    )


def test_ensemble_is_deferred():
    models = load()["deferred_model_families"]

    assert (
        models["ROUTE_ENSEMBLE"]["status"]
        == "DEFER_UNTIL_BASE_OOS_PREDICTIONS_EXIST"
    )

    assert (
        models["GLOBAL_ENSEMBLE"]["status"]
        == "DEFER_UNTIL_BASE_OOS_PREDICTIONS_EXIST"
    )


def test_no_current_market_feature_leakage():
    governance = load()["feature_time_governance"]

    assert (
        governance["current_2026_liquidity"]
        == "PROHIBITED_FROM_HISTORICAL_OOS"
    )

    assert (
        governance["current_2026_source_disagreement"]
        == "PROHIBITED_FROM_HISTORICAL_OOS"
    )

    assert governance["silent_future_feature_fill"] is False


def test_pooled_models_require_product_holdout():
    families = load()["base_model_families"]

    for name in (
        "RIDGE_REGRESSION",
        "HUBER_REGRESSION",
        "RANDOM_FOREST",
        "GRADIENT_BOOSTING",
        "PEER_MEDIAN_RETURN",
        "PEER_WEIGHTED_RETURN",
    ):
        assert families[name]["product_holdout"] is True


def test_random_models_are_reproducible():
    families = load()["base_model_families"]

    assert (
        families["RANDOM_FOREST"]["random_state"]
        == 20260809
    )

    assert (
        families["GRADIENT_BOOSTING"]["random_state"]
        == 20260809
    )


def test_baseline_duplicates_are_not_independent_models():
    governance = load()["baseline_dimension_governance"]

    assert (
        governance[
            "duplicate_baseline_cells_may_be_silently_counted_as_independent_models"
        ]
        is False
    )


def test_downstream_outputs_remain_blocked():
    auth = load()["authorization"]

    assert auth["ensemble_execution"] is False
    assert auth["persistent_model_treatment"] is False
    assert auth["persistent_exclusion"] is False
    assert auth["production_model_selection"] is False
    assert auth["monte_carlo_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False