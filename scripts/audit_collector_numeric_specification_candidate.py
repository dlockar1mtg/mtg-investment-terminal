from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "config/mtg/governance/collector_numeric_specification_candidate_v1.json"
DEFAULT_OUTPUT = ROOT / "data/operations/collector_numeric_methodology/candidate_specification_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the inactive Collector numeric specification candidate.")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.spec.read_text(encoding="utf-8"))
    failures: list[str] = []

    if payload.get("status") != "CANDIDATE_INACTIVE":
        failures.append("STATUS_NOT_CANDIDATE_INACTIVE")
    for field in (
        "exact_numeric_specification_approved",
        "methodology_activated",
        "projection_authorized",
        "purchase_recommendation_authorized",
    ):
        if payload.get(field) is not False:
            failures.append(f"{field.upper()}_MUST_REMAIN_FALSE")

    methods = payload.get("methods", {})
    expected_methods = {
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED",
        "FUNDAMENTAL_COMPARABLE_HYBRID",
    }
    if set(methods) != expected_methods:
        failures.append("METHOD_SET_MISMATCH")

    for method, config in methods.items():
        weights = [
            float(config.get("history_weight", 0.0)),
            float(config.get("comparable_weight", 0.0)),
            float(config.get("fundamental_weight", 0.0)),
        ]
        if abs(sum(weights) - 1.0) > 1e-9:
            failures.append(f"{method}:WEIGHTS_DO_NOT_SUM_TO_ONE")
        if config.get("approval_status") != "CANDIDATE_NOT_OWNER_APPROVED":
            failures.append(f"{method}:INVALID_APPROVAL_STATUS")

    direct = methods.get("DIRECT_HISTORY_CALIBRATED", {})
    window_weights = direct.get("candidate_window_weights", {})
    if abs(sum(float(value) for value in window_weights.values()) - 1.0) > 1e-9:
        failures.append("DIRECT_HISTORY_WINDOW_WEIGHTS_DO_NOT_SUM_TO_ONE")

    scenario = payload.get("scenario_construction", {})
    if scenario.get("hard_caps_enabled") is not False:
        failures.append("HARD_CAPS_MUST_REMAIN_DISABLED")
    if scenario.get("extreme_values_clipped") is not False:
        failures.append("EXTREME_VALUES_MUST_NOT_BE_CLIPPED")

    freshness = payload.get("freshness", {})
    if freshness.get("intended_refresh_frequency") != "DAILY":
        failures.append("DAILY_REFRESH_INTENT_MISSING")
    if freshness.get("warning_threshold_days") is not None:
        failures.append("FRESHNESS_WARNING_THRESHOLD_PREMATURELY_SET")
    if freshness.get("fail_closed_threshold_days") is not None:
        failures.append("FRESHNESS_FAIL_THRESHOLD_PREMATURELY_SET")

    extreme = payload.get("extreme_forecast_review", {})
    if extreme.get("hard_caps_enabled") is not False:
        failures.append("EXTREME_REVIEW_HARD_CAPS_MUST_REMAIN_DISABLED")
    if extreme.get("clipping_enabled") is not False:
        failures.append("EXTREME_REVIEW_CLIPPING_MUST_REMAIN_DISABLED")
    if extreme.get("review_thresholds") is not None:
        failures.append("EXTREME_REVIEW_THRESHOLDS_PREMATURELY_SET")

    purchase = payload.get("purchase_analysis", {})
    if purchase.get("recommendation_labels_enabled") is not False:
        failures.append("PURCHASE_LABELS_MUST_REMAIN_DISABLED")
    if purchase.get("decision_thresholds") is not None:
        failures.append("PURCHASE_THRESHOLDS_PREMATURELY_SET")
    if purchase.get("purchase_recommendation_authorized") is not False:
        failures.append("PURCHASE_RECOMMENDATION_MUST_REMAIN_UNAUTHORIZED")

    summary = {
        "audit_name": "Collector Numeric Specification Candidate Audit",
        "audit_version": "1.0.0",
        "candidate_method_count": len(methods),
        "exact_numeric_specification_approved": payload.get("exact_numeric_specification_approved"),
        "methodology_activated": payload.get("methodology_activated"),
        "projection_authorized": payload.get("projection_authorized"),
        "purchase_recommendation_authorized": payload.get("purchase_recommendation_authorized"),
        "freshness_thresholds_set": any(
            freshness.get(name) is not None
            for name in ("warning_threshold_days", "fail_closed_threshold_days")
        ),
        "extreme_review_thresholds_set": extreme.get("review_thresholds") is not None,
        "purchase_thresholds_set": purchase.get("decision_thresholds") is not None,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
        "governing_note": "This audit validates candidate completeness and inactivity only. It does not approve or activate numeric methodology.",
    }

    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / "collector_numeric_specification_candidate_summary.json"
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
