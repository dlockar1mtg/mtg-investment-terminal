from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_early_lifecycle_breakout_replay/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    cases_path = OUT / "collector_early_lifecycle_breakout_replay_cases.csv"
    summary_csv_path = OUT / "collector_early_lifecycle_breakout_replay_summary.csv"
    summary_json_path = OUT / "collector_early_lifecycle_breakout_replay_summary.json"
    for path in [cases_path, summary_csv_path, summary_json_path]:
        if not path.exists():
            failures.append(f"missing_output:{path.name}")

    cases = pd.read_csv(cases_path, low_memory=False) if cases_path.exists() else pd.DataFrame()
    metrics = pd.read_csv(summary_csv_path, low_memory=False) if summary_csv_path.exists() else pd.DataFrame()
    summary = json.loads(summary_json_path.read_text(encoding="utf-8")) if summary_json_path.exists() else {}

    if cases.empty:
        failures.append("replay_cases_empty")
    else:
        required = {
            "product_key", "product_name", "decision_cutoff", "product_age_months",
            "early_lifecycle_band", "forecast_signal", "realized_return_365",
            "future_information_used_in_forecast", "historical_outcome_used_for_scoring_only",
        }
        if not required.issubset(cases.columns):
            failures.append("required_case_fields_missing")
        if cases["product_key"].astype(str).str.strip().eq("").any():
            failures.append("blank_product_keys")
        if cases["future_information_used_in_forecast"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_detected")
        if not cases["historical_outcome_used_for_scoring_only"].astype(str).str.lower().eq("true").all():
            failures.append("outcome_scoring_only_control_failed")
        allowed = {"LAUNCH_PRICE_DISCOVERY", "INITIAL_SUPPLY_ABSORPTION", "STABILIZATION", "EARLY_ACCUMULATION"}
        if not set(cases["early_lifecycle_band"]).issubset(allowed):
            failures.append("invalid_age_band")

    if metrics.empty:
        failures.append("replay_metrics_empty")
    else:
        if "ALL_EARLY_LIFECYCLE" not in set(metrics["scope"]):
            failures.append("overall_scope_missing")
        required_metrics = {
            "case_count", "product_count", "cutoff_count", "breakout_count_25",
            "breakout_count_50", "breakout_count_70", "breakout_recall_25",
            "breakout_recall_50", "breakout_recall_70", "false_negative_rate_25",
            "false_negative_rate_50", "false_negative_rate_70", "top_quantile_capture_25",
            "top_quantile_capture_50", "top_quantile_capture_70", "false_positive_rate_25",
            "false_positive_rate_50", "false_positive_rate_70", "mean_missed_upside_25",
            "mean_missed_upside_50", "mean_missed_upside_70", "rank_correlation", "top_bottom_spread",
        }
        if not required_metrics.issubset(metrics.columns):
            failures.append("required_metrics_missing")

    if summary.get("future_information_used_in_forecast") is not False:
        failures.append("summary_future_information_control_failed")
    if summary.get("historical_outcome_used_for_scoring_only") is not True:
        failures.append("summary_outcome_scoring_control_failed")
    for key in [
        "methodology_change_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Early-Lifecycle Breakout Replay Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
