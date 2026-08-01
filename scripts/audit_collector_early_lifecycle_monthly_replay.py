from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_early_lifecycle_monthly_replay/candidate_v1_0_0"


def safe_read(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    cases_path = OUT / "collector_early_lifecycle_monthly_replay_cases.csv"
    diagnostics_path = OUT / "collector_early_lifecycle_monthly_replay_schema_diagnostics.csv"
    summary_path = OUT / "collector_early_lifecycle_monthly_replay_summary.json"
    cases = safe_read(cases_path)
    diagnostics = safe_read(diagnostics_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    if cases.empty:
        failures.append("monthly_replay_cases_empty")
    else:
        required = {
            "product_key", "product_name", "decision_cutoff", "release_date",
            "product_age_months", "early_lifecycle_band", "current_price_at_cutoff",
            "forward_observation_date", "forward_gap_months", "forward_price_365",
            "realized_return_365", "breakout_25", "breakout_50", "breakout_70",
            "future_information_used_in_features", "forward_price_used_for_scoring_only",
        }
        if not required.issubset(cases.columns):
            failures.append("required_case_fields_missing")
        if cases["product_key"].astype(str).str.strip().eq("").any():
            failures.append("blank_product_keys")
        if cases["future_information_used_in_features"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_used_in_features")
        if not cases["forward_price_used_for_scoring_only"].astype(str).str.lower().eq("true").all():
            failures.append("forward_price_scoring_control_failed")
        allowed = {"LAUNCH_PRICE_DISCOVERY", "INITIAL_SUPPLY_ABSORPTION", "STABILIZATION", "EARLY_ACCUMULATION"}
        if not set(cases["early_lifecycle_band"]).issubset(allowed):
            failures.append("invalid_age_band")
        gaps = pd.to_numeric(cases["forward_gap_months"], errors="coerce")
        if gaps.isna().any() or ((gaps < 11) | (gaps > 13)).any():
            failures.append("forward_gap_outside_11_13_months")
        if pd.to_numeric(cases["current_price_at_cutoff"], errors="coerce").le(0).any():
            failures.append("nonpositive_current_price")
        if pd.to_numeric(cases["forward_price_365"], errors="coerce").le(0).any():
            failures.append("nonpositive_forward_price")

    if diagnostics.empty:
        failures.append("schema_diagnostics_empty")
    else:
        for column in ["name_column", "date_column", "release_column", "price_column"]:
            if column not in diagnostics.columns or diagnostics.iloc[0][column] == "UNMAPPED":
                failures.append(f"schema_mapping_missing:{column}")

    if summary.get("future_information_used_in_features") is not False:
        failures.append("summary_future_information_control_failed")
    if summary.get("forward_price_used_for_scoring_only") is not True:
        failures.append("summary_forward_price_control_failed")
    if summary.get("complete_negative_case_retention_required") is not True:
        failures.append("negative_case_retention_not_required")
    for key in [
        "methodology_change_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Early-Lifecycle Monthly Replay Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
