from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "mtg" / "governance" / "collector_walk_forward_backtest_foundation_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def audit(config_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    if not config_path.exists():
        return {
            "audit_name": "Collector Walk-Forward Backtest Foundation Audit",
            "audit_version": "1.0.0",
            "status": "FAIL",
            "failure_count": 1,
            "failures": [f"Missing config: {config_path}"],
        }

    config = load_json(config_path)
    snapshots = config.get("snapshot_contract", {})
    outcomes = config.get("outcome_contract", {})
    evaluation = config.get("evaluation_contract", {})
    search = config.get("parameter_search_contract", {})
    controls = config.get("recommendation_controls", {})
    authorizations = config.get("authorizations", {})

    required_snapshot_fields = {
        "snapshot_id", "decision_date", "investment_product_id", "forecast_method",
        "current_price", "history_cutoff_date", "evidence_cutoff_date",
        "comparable_cutoff_date", "model_candidate_version",
    }
    actual_snapshot_fields = set(snapshots.get("required_keys", []))
    missing_snapshot_fields = sorted(required_snapshot_fields - actual_snapshot_fields)
    if missing_snapshot_fields:
        failures.append(f"Missing snapshot fields: {missing_snapshot_fields}")

    for key in (
        "future_information_prohibited",
        "as_of_join_required",
        "route_reconstruction_required",
        "comparable_reconstruction_required",
        "missing_input_must_be_visible",
    ):
        if snapshots.get(key) is not True:
            failures.append(f"snapshot_contract.{key} must be true")

    if outcomes.get("required_horizons_days") != [365, 1095, 1825]:
        failures.append("Outcome horizons must be 365, 1095, and 1825 days")
    if outcomes.get("unmatured_outcomes_excluded_from_scoring") is not True:
        failures.append("Unmatured outcomes must be excluded from scoring")
    if outcomes.get("unmatured_outcomes_retained_for_future_matching") is not True:
        failures.append("Unmatured outcomes must be retained")

    for key in (
        "walk_forward_required",
        "holdout_required",
        "route_specific_results_required",
        "release_age_results_required",
        "early_opportunity_results_required",
        "cost_adjusted_results_required",
        "risk_adjusted_results_required",
        "interval_coverage_required",
        "parameter_stability_required",
    ):
        if evaluation.get(key) is not True:
            failures.append(f"evaluation_contract.{key} must be true")

    if search.get("baseline_candidate_must_run_first") is not True:
        failures.append("Baseline candidate must run before parameter search")
    if search.get("objective_metric_weights") is not None:
        failures.append("Objective metric weights must remain unset")
    if search.get("minimum_improvement_required") is not None:
        failures.append("Minimum improvement must remain unset")
    if search.get("maximum_downside_degradation") is not None:
        failures.append("Maximum downside degradation must remain unset")
    if search.get("minimum_sample_thresholds") is not None:
        failures.append("Minimum sample thresholds must remain unset")

    if controls.get("recommendation_generation_allowed") is not True:
        failures.append("Recommendation generation should be allowed")
    if controls.get("automatic_model_update_allowed") is not False:
        failures.append("Automatic model updates must be false")
    if controls.get("owner_approval_required") is not True:
        failures.append("Owner approval must be required")
    if controls.get("recertification_required") is not True:
        failures.append("Recertification must be required")
    if controls.get("active_model_file_may_be_modified") is not False:
        failures.append("Backtest foundation must not modify active model files")

    for key in (
        "exact_numeric_specification_approved",
        "methodology_activated",
        "projection_authorized",
        "purchase_recommendation_authorized",
    ):
        if authorizations.get(key) is not False:
            failures.append(f"authorizations.{key} must remain false")

    return {
        "audit_name": "Collector Walk-Forward Backtest Foundation Audit",
        "audit_version": "1.0.0",
        "snapshot_required_field_count": len(snapshots.get("required_keys", [])),
        "outcome_horizon_count": len(outcomes.get("required_horizons_days", [])),
        "evaluation_metric_family_count": len(evaluation.get("required_metric_families", [])),
        "recommendation_generation_allowed": controls.get("recommendation_generation_allowed"),
        "automatic_model_update_allowed": controls.get("automatic_model_update_allowed"),
        "owner_approval_required": controls.get("owner_approval_required"),
        "recertification_required": controls.get("recertification_required"),
        "projection_authorized": authorizations.get("projection_authorized"),
        "purchase_recommendation_authorized": authorizations.get("purchase_recommendation_authorized"),
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
        "governing_note": "This audit validates a time-correct, recommendation-only backtest foundation. It does not run forecasts or activate parameter changes.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = audit(args.config)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and result["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
