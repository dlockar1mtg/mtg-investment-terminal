from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_comparable_model_tournament_calibration.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_comparable_model_tournament_calibration_contract_v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("precollector_model_tournament", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_keeps_all_downstream_authority_false():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["expected_active_product_count"] == 79
    assert contract["expected_required_comparable_target_count"] == 23
    assert contract["expected_approved_comparable_rows"] == 369
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False
    assert contract["uip_delivery_authorized"] is False


def test_candidate_models_are_explicit_and_deterministic():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["candidate_models"] == [
        "APPROVED_POLICY_WEIGHTED",
        "INVERSE_DISTANCE",
        "RANK_DECAY",
        "ROBUST_MEDIAN",
    ]


def test_normalized_weights_sum_to_one():
    module = load_module()
    values = pd.Series([0.5, 0.25, 0.25])
    result = module.normalized(values)
    assert abs(float(result.sum()) - 1.0) < 1e-12


def test_normalized_weights_fall_back_to_equal_weights():
    module = load_module()
    result = module.normalized(pd.Series([0.0, 0.0]))
    assert list(result.round(6)) == [0.5, 0.5]


def test_approved_policy_model_uses_approved_weights():
    module = load_module()
    frame = pd.DataFrame({
        "approved_contribution_weight": [0.8, 0.2],
        "comparable_distance_score": [1.0, 2.0],
        "comparable_rank": [1, 2],
    })
    weights = module.model_weights(frame, "APPROVED_POLICY_WEIGHTED")
    assert list(weights.round(6)) == [0.8, 0.2]


def test_inverse_distance_prefers_closer_donor():
    module = load_module()
    frame = pd.DataFrame({
        "approved_contribution_weight": [0.5, 0.5],
        "comparable_distance_score": [0.5, 4.0],
        "comparable_rank": [1, 2],
    })
    weights = module.model_weights(frame, "INVERSE_DISTANCE")
    assert weights.iloc[0] > weights.iloc[1]


def test_rank_decay_prefers_rank_one():
    module = load_module()
    frame = pd.DataFrame({
        "approved_contribution_weight": [0.5, 0.5],
        "comparable_distance_score": [1.0, 1.0],
        "comparable_rank": [1, 2],
    })
    weights = module.model_weights(frame, "RANK_DECAY")
    assert weights.iloc[0] > weights.iloc[1]


def test_robust_median_prediction_uses_median_price():
    module = load_module()
    frame = pd.DataFrame({
        "candidate_current_price": [100.0, 200.0, 1000.0],
        "approved_contribution_weight": [0.4, 0.4, 0.2],
        "comparable_distance_score": [1.0, 2.0, 3.0],
        "comparable_rank": [1, 2, 3],
    })
    assert module.prediction(frame, "ROBUST_MEDIAN") == 200.0


def test_geometric_prediction_is_positive():
    module = load_module()
    frame = pd.DataFrame({
        "candidate_current_price": [100.0, 400.0],
        "approved_contribution_weight": [0.5, 0.5],
        "comparable_distance_score": [1.0, 1.0],
        "comparable_rank": [1, 2],
    })
    predicted = module.prediction(frame, "APPROVED_POLICY_WEIGHTED")
    assert predicted > 0
    assert round(predicted, 6) == 200.0
