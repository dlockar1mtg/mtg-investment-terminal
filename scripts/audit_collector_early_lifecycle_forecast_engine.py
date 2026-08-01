from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_early_lifecycle_forecast_engine_v1.json"
OUT = ROOT / "data/operations/collector_early_lifecycle_forecast_engine/candidate_v1_0_0"
NA = "NOT_AVAILABLE"


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False, keep_default_na=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    failures: list[str] = []

    output_path = OUT / "collector_early_lifecycle_complete_universe.csv"
    comparable_path = OUT / "collector_early_lifecycle_age_aligned_comparables.csv"
    summary_path = OUT / "collector_early_lifecycle_forecast_engine_summary.json"
    for path in [output_path, comparable_path, summary_path]:
        if not path.exists():
            failures.append(f"missing_output:{path.name}")

    output = read_csv(output_path)
    summary: dict[str, object] = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append("summary_unreadable")

    required = set(cfg["required_output_fields"])
    if output.empty:
        failures.append("complete_universe_output_empty")
    else:
        if not required.issubset(output.columns):
            failures.append("required_fields_missing")
        if output["product_name"].duplicated().any():
            failures.append("duplicate_products")
        if output.isna().any().any():
            failures.append("null_values_detected")
        blanks = output.astype(str).apply(lambda s: s.str.strip().eq("").any()).any()
        if blanks:
            failures.append("blank_values_detected")
        allowed = {"PROVISIONAL_365", "SCENARIO_ELIGIBLE", "BLOCKED"}
        if not set(output["forecast_status"]).issubset(allowed):
            failures.append("invalid_status")
        non_provisional_points = (output["forecast_status"] != "PROVISIONAL_365") & (output["forecast_center_365"] != NA)
        if non_provisional_points.any():
            failures.append("point_forecast_exposed_without_provisional_status")
        scenario_fields = ["bear_return_365", "base_return_365", "bull_return_365", "forecast_lower_365", "forecast_upper_365"]
        if output[scenario_fields].isin(["", NA]).any().any():
            failures.append("scenario_fields_missing")
        blocked = output["forecast_status"] == "BLOCKED"
        if blocked.any() and output.loc[blocked, "blocked_reason"].isin(["", NA, "NOT_APPLICABLE"]).any():
            failures.append("blocked_reason_missing")
        if output["next_evidence_requirement"].isin(["", NA]).any():
            failures.append("next_evidence_requirement_missing")
        if output["next_review_trigger"].isin(["", NA]).any():
            failures.append("next_review_trigger_missing")
        if output["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_detected")

    if summary.get("complete_universe_product_count") != summary.get("output_product_count"):
        failures.append("summary_universe_count_mismatch")
    if summary.get("missing_product_count") != 0:
        failures.append("products_missing_from_layout")
    if summary.get("all_products_have_status") is not True:
        failures.append("status_completeness_failed")
    if summary.get("all_required_fields_populated") is not True:
        failures.append("field_completeness_failed")
    if summary.get("future_information_used") is not False:
        failures.append("summary_future_information_control_failed")

    for key in [
        "early_lifecycle_shadow_implementation_authorized", "provisional_365_authorized",
        "scenario_output_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Early-Lifecycle Forecast Engine Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
