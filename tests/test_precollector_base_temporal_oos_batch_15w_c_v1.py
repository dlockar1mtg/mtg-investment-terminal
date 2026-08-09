import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_base_temporal_oos_batch_15w_c_v1.json"
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
    ] == "15W-C"

    assert contract[
        "model_families"
    ] == [
        "PEER_MEDIAN_RETURN",
        "PEER_WEIGHTED_RETURN",
    ]

    assert contract[
        "governed_matrix_cells"
    ] == 72


def test_peer_parameters():

    contract = load()

    assert contract[
        "minimum_peer_rows"
    ] == 5

    assert contract[
        "weighted_neighbor_count"
    ] == 15


def test_temporal_rules():

    rules = load()[
        "temporal_training_rule"
    ]

    assert rules[
        "endpoint_must_mature_by_validation_origin"
    ] is True

    assert rules[
        "same_product_prior_matured_examples_allowed"
    ] is True

    assert rules[
        "future_examples_allowed"
    ] is False

    assert rules[
        "current_market_feature_leakage_allowed"
    ] is False

    assert rules[
        "random_time_split_allowed"
    ] is False


def test_median_semantic_duplicates():

    rule = load()[
        "semantic_duplicate_rule"
    ]

    assert rule[
        "peer_median_uses_feature_variant"
    ] is False

    assert rule[
        "peer_median_duplicate_feature_cells_independent"
    ] is False

    assert rule[
        "peer_weighted_uses_feature_variant"
    ] is True


def test_downstream_blocked():

    auth = load()[
        "authorization"
    ]

    assert auth[
        "current_batch_execution"
    ] is True

    assert auth[
        "tree_batch_execution"
    ] is False

    assert auth[
        "base_reconciliation"
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