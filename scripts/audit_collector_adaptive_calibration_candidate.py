from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/mtg/governance/collector_adaptive_calibration_candidate_v1.json"
DEFAULT_OUTPUT = ROOT / "data/operations/collector_adaptive_calibration/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit inactivity and governance of the Collector adaptive calibration candidate.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.config.read_text(encoding="utf-8"))
    failures: list[str] = []

    if payload.get("status") != "PROPOSED_INACTIVE":
        failures.append("STATUS_NOT_PROPOSED_INACTIVE")
    if payload.get("active_model_auto_update_allowed") is not False:
        failures.append("AUTOMATIC_MODEL_UPDATE_NOT_BLOCKED")
    if payload.get("owner_approval_required_for_activation") is not True:
        failures.append("OWNER_APPROVAL_NOT_REQUIRED")
    if payload.get("recertification_required_after_material_change") is not True:
        failures.append("RECERTIFICATION_NOT_REQUIRED")
    if payload.get("projection_authorized") is not False:
        failures.append("PROJECTION_AUTHORIZED")
    if payload.get("purchase_recommendation_authorized") is not False:
        failures.append("PURCHASE_AUTHORIZED")

    design = payload.get("backtest_design", {})
    for field in (
        "walk_forward_required",
        "time_order_must_be_preserved",
        "future_information_prohibited",
        "route_specific_evaluation_required",
        "release_age_cohorts_required",
        "transaction_costs_required",
        "liquidity_effects_required",
        "holdout_period_required",
    ):
        if design.get(field) is not True:
            failures.append(f"BACKTEST_REQUIREMENT_MISSING:{field}")

    recommendation = payload.get("recommendation_contract", {})
    if recommendation.get("automatic_activation") is not False:
        failures.append("RECOMMENDATION_AUTOMATIC_ACTIVATION_ENABLED")
    if recommendation.get("default_owner_approval_status") != "NOT_REQUESTED":
        failures.append("INVALID_DEFAULT_OWNER_APPROVAL_STATUS")

    controls = payload.get("change_controls", {})
    if controls.get("all_numeric_controls_status") != "UNSET_PENDING_BACKTEST_AND_OWNER_APPROVAL":
        failures.append("NUMERIC_CHANGE_CONTROLS_PREMATURELY_SET")

    summary = {
        "audit_name": "Collector Adaptive Calibration Candidate Audit",
        "audit_version": "1.0.0",
        "candidate_parameter_count": len(payload.get("candidate_parameters", [])),
        "recommendation_generation_allowed": payload.get("recommendation_generation_allowed"),
        "automatic_model_update_allowed": payload.get("active_model_auto_update_allowed"),
        "owner_approval_required": payload.get("owner_approval_required_for_activation"),
        "recertification_required": payload.get("recertification_required_after_material_change"),
        "projection_authorized": payload.get("projection_authorized"),
        "purchase_recommendation_authorized": payload.get("purchase_recommendation_authorized"),
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
        "governing_note": "Backtests may recommend parameter changes, but they cannot alter the active model without owner approval and recertification.",
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "collector_adaptive_calibration_candidate_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
