from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import build_collector_v1_first_year_breakout_reconstruction_plan as build

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_first_year_breakout_reconstruction_plan"


def test_first_year_breakout_reconstruction_plan() -> None:
    assert build.main([]) == 0
    summary = json.loads((OUT / "collector_v1_first_year_breakout_reconstruction_plan_summary.json").read_text(encoding="utf-8"))
    matrix = pd.read_csv(OUT / "collector_v1_first_year_breakout_reconstruction_matrix.csv", dtype=str).fillna("")

    assert summary["status"] == "PASS_COLLECTOR_V1_FIRST_YEAR_BREAKOUT_RECONSTRUCTION_PLAN"
    assert summary["governed_product_count"] == 50
    assert summary["evaluation_checkpoints_days"] == [0, 30, 60, 90, 120, 180, 270, 365]
    assert summary["product_checkpoint_rows"] == 400
    assert summary["historical_supply_demand_policy"] == "USE_ONLY_WHEN_POINT_IN_TIME_SUPPORTED"
    assert summary["all_supply_demand_metrics_required_for_replay"] is False
    assert summary["unavailable_features_are_zero"] is False
    assert summary["feature_availability_audit_required_before_panel_build"] is True
    assert summary["lifecycle_panel_reconstruction_authorized"] is True
    assert summary["breakout_model_execution_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["critical_failures"] == []

    assert len(matrix) == 400
    assert matrix.groupby("tcgplayer_product_id")["checkpoint_age_days"].nunique().eq(8).all()
    for column in (
        "point_in_time_replay_required",
        "future_information_prohibited",
        "feature_availability_ledger_required",
        "unavailable_features_remain_missing",
        "historical_feature_invention_prohibited",
        "historical_zero_fill_prohibited",
        "supply_demand_if_available_at_checkpoint",
        "compatible_feature_set_model_required",
        "feature_coverage_confidence_adjustment_required",
        "core_replay_lane_required",
        "enhanced_replay_lane_allowed_when_supported",
        "current_production_lane_separate_from_replay_validation",
        "breakout_definition_tournament_required",
        "breakout_model_tournament_required",
        "entry_timing_model_required",
        "missed_entry_cost_required",
        "opportunity_capture_required",
        "late_signal_penalty_required",
        "mtg_owned_output",
    ):
        assert matrix[column].str.lower().eq("true").all()
    assert matrix["all_supply_demand_metrics_required_at_checkpoint"].str.lower().eq("false").all()
    assert matrix["uip_may_rewrite_output"].str.lower().eq("false").all()
    assert matrix["purchase_recommendation_authorized"].str.lower().eq("false").all()

    star_trek = matrix[matrix["tcgplayer_product_id"].eq("706142")]
    assert len(star_trek) == 8
    assert star_trek["comparable_route"].str.lower().eq("true").all()
    assert star_trek["selected_comparable_paths_required"].str.lower().eq("true").all()


def test_contract_penalizes_late_discovery() -> None:
    contract = json.loads((ROOT / "config/mtg/standards/collector_first_year_breakout_entry_timing_contract_v1.json").read_text(encoding="utf-8"))
    metrics = set(contract["required_metrics"])
    states = set(contract["required_states"])
    assert {
        "breakout_recall",
        "early_entry_precision",
        "median_signal_lead_days",
        "missed_entry_cost_pct",
        "opportunity_capture_pct",
        "appreciation_already_realized_pct",
        "remaining_expected_upside_pct",
    }.issubset(metrics)
    assert {"LATE_STAGE_MOMENTUM", "OPPORTUNITY_MOSTLY_REALIZED", "OVEREXTENDED"}.issubset(states)
    assert contract["breakout_label_policy"]["fixed_single_threshold_prohibited"] is True
    assert contract["breakout_label_policy"]["candidate_definitions_must_compete"] is True


def test_contract_is_feature_availability_aware() -> None:
    contract = json.loads((ROOT / "config/mtg/standards/collector_first_year_breakout_entry_timing_contract_v1.json").read_text(encoding="utf-8"))
    design = contract["required_backtest_design"]
    policy = contract["historical_evidence_availability_policy"]
    outputs = set(contract["required_product_outputs"])

    assert design["feature_availability_ledger_required"] is True
    assert design["unavailable_features_must_remain_missing"] is True
    assert design["historical_feature_invention_prohibited"] is True
    assert design["historical_zero_fill_prohibited"] is True
    assert design["model_candidates_must_match_available_feature_set"] is True
    assert design["confidence_must_reflect_feature_coverage"] is True

    assert "UNAVAILABLE_AT_CHECKPOINT" in policy["availability_states"]
    assert "SOURCE_NOT_YET_OPERATING" in policy["availability_states"]
    assert "OBSERVATION_TIMESTAMP_UNVERIFIED" in policy["availability_states"]
    assert "UNAVAILABLE_AT_CHECKPOINT" not in policy["eligible_states_for_model_input"]
    assert "SOURCE_NOT_YET_OPERATING" not in policy["eligible_states_for_model_input"]
    assert "OBSERVATION_TIMESTAMP_UNVERIFIED" not in policy["eligible_states_for_model_input"]

    assert {
        "feature_coverage_ratio",
        "supply_demand_coverage_class",
        "historical_replay_lane",
        "feature_missingness_summary",
        "confidence_adjustment_for_feature_coverage",
    }.issubset(outputs)
