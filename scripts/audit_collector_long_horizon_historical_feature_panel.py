from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_long_horizon_historical_feature_panel/candidate_v1_0_0"


def read_csv_safe(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except (pd.errors.EmptyDataError, OSError, UnicodeDecodeError):
        return pd.DataFrame()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    summary_path = OUT / "collector_long_horizon_historical_feature_panel_summary.json"
    panel_path = OUT / "collector_long_horizon_decision_feature_panel.csv"
    coverage_path = OUT / "collector_long_horizon_feature_coverage.csv"
    lineage_path = OUT / "collector_long_horizon_source_lineage.csv"

    for path in [summary_path, panel_path, coverage_path, lineage_path]:
        if not path.exists():
            failures.append(f"missing_output:{path.name}")

    summary: dict[str, object] = {}
    panel = read_csv_safe(panel_path) if panel_path.exists() else pd.DataFrame()
    coverage = read_csv_safe(coverage_path) if coverage_path.exists() else pd.DataFrame()
    lineage = read_csv_safe(lineage_path) if lineage_path.exists() else pd.DataFrame()
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            failures.append("summary_unreadable")

    if panel.empty:
        failures.append("feature_panel_empty")
    else:
        if "future_information_used" not in panel.columns:
            failures.append("future_information_control_missing")
        elif panel["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_control_failed")
        if "release_date" not in panel.columns:
            failures.append("release_date_missing")
        if "since_history_start_cagr" not in panel.columns:
            failures.append("since_history_start_cagr_missing")
        if "since_release_cagr" not in panel.columns:
            failures.append("since_release_cagr_missing")
        elif "release_date" in panel.columns:
            invalid = panel["release_date"].fillna("").astype(str).eq("") & panel["since_release_cagr"].notna()
            if invalid.any():
                failures.append("since_release_cagr_without_release_identity")

    if summary.get("current_only_fundamentals_used") is not False:
        failures.append("current_only_fundamentals_used")
    roles = set(lineage["source_role"].astype(str)) if "source_role" in lineage.columns else set()
    if not {"price_history", "release_registry", "walk_forward_outcomes"}.issubset(roles):
        failures.append("canonical_lineage_incomplete")

    required = {
        "product_age_months", "product_age_route", "return_3_month", "return_6_month", "return_12_month",
        "cagr_2_year", "cagr_3_year", "since_history_start_cagr", "since_release_cagr",
        "collector_category_cagr", "trailing_12_month_volatility", "maximum_12_month_drawdown",
        "positive_month_rate", "return_persistence", "forecast_extremeness", "data_quality_grade",
    }
    covered = set(coverage["derived_feature"].astype(str)) if "derived_feature" in coverage.columns else set()
    if not required.issubset(covered):
        failures.append("feature_coverage_contract_incomplete")

    for key in [
        "candidate_methodology_change_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Long-Horizon Historical Feature Panel Audit",
        "audit_version": "1.0.2",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
