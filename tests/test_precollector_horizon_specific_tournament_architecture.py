from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_horizon_specific_tournament_architecture_contract_v1.json"
BUILDER = ROOT / "scripts/build_precollector_horizon_specific_tournament_architecture.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_exact_five_horizons() -> None:
    contract = load_contract()
    assert [(h["horizon_code"], h["horizon_days"]) for h in contract["forecast_horizons"]] == [
        ("D90", 90), ("D180", 180), ("D365", 365), ("Y3", 1095), ("Y5", 1825)
    ]


def test_independent_tournament_required() -> None:
    assert load_contract()["independent_tournament_per_horizon"] is True


def test_all_three_routes_declared() -> None:
    assert set(load_contract()["route_model_families"]) == {
        "DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED", "COMPARABLE_PRODUCT_ADJUSTED"
    }


def test_rank_decay_comparable_candidate_present() -> None:
    assert "RANK_DECAY_WEIGHTED_GROWTH" in load_contract()["route_model_families"]["COMPARABLE_PRODUCT_ADJUSTED"]


def test_baselines_required() -> None:
    assert load_contract()["required_baselines"] == ["NAIVE_LAST_VALUE", "HORIZON_DRIFT_BASELINE"]


def test_rolling_origin_and_uncertainty_required() -> None:
    policy = load_contract()["validation_policy"]
    assert policy["rolling_origin_required"] is True
    assert policy["promotion_requires_uncertainty_output"] is True
    assert policy["no_cross_horizon_winner_reuse_without_competing"] is True


def test_fallback_policy_fail_closed() -> None:
    fallback = load_contract()["fallback_policy"]
    assert fallback["no_candidate_beats_baseline"] == "RETAIN_BASELINE"
    assert fallback["unstable_candidate"] == "REJECT_AND_USE_NEXT_ELIGIBLE_MODEL"


def test_downstream_authority_false() -> None:
    contract = load_contract()
    for key in ["forecast_generation_authorized", "ranking_execution_authorized", "purchase_analysis_authorized", "purchase_recommendation_authorized", "automatic_purchase_execution_authorized", "uip_delivery_authorized"]:
        assert contract[key] is False


def test_next_stage_execution_only() -> None:
    assert load_contract()["next_stage_if_certified"] == "PRECOLLECTOR_HORIZON_SPECIFIC_TOURNAMENT_EXECUTION"


def test_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_horizon_architecture", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
