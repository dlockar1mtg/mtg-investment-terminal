from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_horizon_specific_tournament_architecture_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_horizon_specific_tournament_architecture.py"


def test_contract_has_six_independent_horizons() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["independent_tournament_per_horizon"] is True
    assert [h["days"] for h in payload["forecast_horizons"]] == [90, 180, 365, 730, 1095, 1825]
    assert payload["validation_policy"]["no_cross_horizon_winner_reuse_without_competing"] is True


def test_route_model_families_are_separate() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    families = payload["route_model_families"]
    assert set(families) == {
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED",
    }
    assert "SHRUNK_COMPARABLE_ENSEMBLE" in families["COMPARABLE_PRODUCT_ADJUSTED"]


def test_early_life_policy_targets_350_to_400_entry() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    early = payload["early_life_policy"]
    assert early["entry_price_target_low"] == 350.0
    assert early["entry_price_target_high"] == 400.0
    assert early["late_recognition_warning_price"] == 600.0
    assert early["must_not_require_price_above_late_recognition_warning"] is True
    assert "EARLY_POST_RELEASE" in early["eligible_lifecycle_bands"]


def test_current_supply_demand_is_overlay_only() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    overlay = payload["current_overlay_policy"]
    assert overlay["prohibited_from_backtest_features"] is True
    assert overlay["allowed_only_after_historical_model_forecast"] is True
    assert overlay["may_change_point_forecast"] is False
    assert overlay["may_change_ranking_and_confidence"] is True
    assert overlay["purchase_authorization_separate"] is True


def test_script_builds_required_governance_outputs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for name in [
        "collector_horizon_tournament_registry.csv",
        "collector_horizon_model_family_registry.csv",
        "collector_early_life_entry_registry.csv",
        "collector_current_supply_demand_overlay_registry.csv",
        "collector_horizon_specific_tournament_architecture_summary.json",
    ]:
        assert name in text


def test_script_preserves_horizon_and_overlay_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "independent_winner_required" in text
    assert "current_supply_demand_allowed_in_fit" in text
    assert "must_score_before_600" in text
    assert '"production_forecasting_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text
