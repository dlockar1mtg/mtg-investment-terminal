from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_recovery_contract_is_read_only_and_lane_bound() -> None:
    contract = json.loads((ROOT / "config/mtg/standards/precollector_recovery_state_audit_contract_v1.json").read_text(encoding="utf-8"))
    assert contract["status"] == "READ_ONLY_RECOVERY_AUDIT_AUTHORIZED"
    assert contract["governed_lane"] == "precollector_booster_boxes"
    assert contract["forecast_execution_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_analysis_authorized"] is False


def test_owner_scope_excludes_collector_booster_targets() -> None:
    scope = json.loads((ROOT / "config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json").read_text(encoding="utf-8"))
    assert scope["governed_lane"] == "precollector_booster_boxes"
    assert "Collector Booster boxes" in scope["excluded_product_families"]


def test_reconciliation_requires_owner_review_before_forecasting() -> None:
    contract = json.loads((ROOT / "config/mtg/standards/precollector_universe_reconciliation_contract_v1.json").read_text(encoding="utf-8"))
    assert contract["next_stage_if_certified"] == "OWNER_REVIEW_OF_RECONCILED_UNIVERSE_AND_SOURCE_HIERARCHY"
    assert contract["controls"]["forecast_generation_authorized"] is False


def test_recovery_decision_quarantines_wrong_binding_chain() -> None:
    recovery = json.loads((ROOT / "config/mtg/governance/precollector_lane_boundary_and_recovery_decision_v1.json").read_text(encoding="utf-8"))
    assert recovery["incident"]["classification"] == "UNAPPROVED_CROSS_LANE_TARGET_AUTHORITY_SUBSTITUTION"
    assert recovery["incident"]["collector_source_assets_modified"] is False
    assert recovery["lane_boundary_policy"]["collector_foundation_allowed_as_target_authority"] is False
    assert recovery["current_authorization"]["precollector_universe_state_audit_authorized"] is True
    assert recovery["current_authorization"]["new_precollector_forecast_execution_authorized"] is False


def test_audit_script_has_no_network_or_forecast_execution() -> None:
    text = (ROOT / "scripts/audit_precollector_recovery_state.py").read_text(encoding="utf-8")
    assert "urlopen" not in text
    assert "requests." not in text
    assert "run_precollector_long_horizon_monte_carlo" not in text
    assert "run_precollector_ranking_execution" not in text
    assert "OWNER_REVIEW_OF_PRECOLLECTOR_RECOVERY_STATE" in (ROOT / "config/mtg/standards/precollector_recovery_state_audit_contract_v1.json").read_text(encoding="utf-8")
