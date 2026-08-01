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
    comparables = read_csv(comparable_path)
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
        if output.isna().to_numpy().any():
            failures.append("null_values_detected")
        blank_values = output.astype(str).apply(lambda column: column.str.strip().eq("")).to_numpy().any()
        if blank_values:
            failures.append("blank_values_detected")

        allowed = {"PROVISIONAL_365", "SCENARIO_ELIGIBLE", "UNIVERSAL_MATCHED_365"}
        if not set(output["forecast_status"]).issubset(allowed):
            failures.append("invalid_status")
        if output["forecast_status"].eq("BLOCKED").any():
            failures.append("blocked_status_detected")
        if output["forecast_center_365"].isin(["", NA]).any():
            failures.append("point_forecast_missing")

        scenario_fields = [
            "bear_return_365", "base_return_365", "bull_return_365",
            "forecast_lower_365", "forecast_upper_365",
        ]
        if output[scenario_fields].isin(["", NA]).any().any():
            failures.append("scenario_fields_missing")
        if output["age_aligned_comparable_group"].isin(["", NA]).any():
            failures.append("match_or_universal_prior_missing")
        if output["match_tier"].isin(["", NA]).any():
            failures.append("match_tier_missing")
        if output["match_quality"].isin(["", NA]).any():
            failures.append("match_quality_missing")
        if output["forecast_basis"].isin(["", NA]).any():
            failures.append("forecast_basis_missing")
        if output["blocked_reason"].ne("NOT_APPLICABLE").any():
            failures.append("blocked_reason_present_in_no_block_engine")
        if output["next_evidence_requirement"].isin(["", NA]).any():
            failures.append("next_evidence_requirement_missing")
        if output["next_review_trigger"].isin(["", NA]).any():
            failures.append("next_review_trigger_missing")
        if output["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_detected")

    if comparables.empty:
        failures.append("comparable_or_prior_lineage_empty")
    else:
        required_comparable = {
            "target_product", "comparable_product", "match_tier", "match_quality",
            "comparable_weight", "peer_signal_at_cutoff", "future_information_used",
        }
        if not required_comparable.issubset(comparables.columns):
            failures.append("comparable_lineage_contract_incomplete")
        if comparables.get("future_information_used", pd.Series(dtype=str)).astype(str).str.lower().eq("true").any():
            failures.append("comparable_future_information_detected")
        targets = set(comparables.get("target_product", pd.Series(dtype=str)).astype(str))
        products = set(output.get("product_name", pd.Series(dtype=str)).astype(str))
        if not products.issubset(targets):
            failures.append("products_without_comparable_or_prior_lineage")

    if summary.get("complete_universe_product_count") != summary.get("output_product_count"):
        failures.append("summary_universe_count_mismatch")
    if summary.get("missing_product_count") != 0:
        failures.append("products_missing_from_layout")
    if summary.get("blocked_count") != 0:
        failures.append("summary_blocked_count_not_zero")
    if summary.get("all_products_have_status") is not True:
        failures.append("status_completeness_failed")
    if summary.get("all_products_have_point_forecast") is not True:
        failures.append("point_forecast_completeness_failed")
    if summary.get("all_products_have_match_or_prior") is not True:
        failures.append("match_completeness_failed")
    if summary.get("all_required_fields_populated") is not True:
        failures.append("field_completeness_failed")
    if summary.get("future_information_used") is not False:
        failures.append("summary_future_information_control_failed")

    for key in [
        "early_lifecycle_shadow_implementation_authorized",
        "provisional_365_authorized",
        "scenario_output_authorized",
        "universal_matched_365_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
        "technical_freeze_authorized",
        "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Early-Lifecycle Forecast Engine Audit",
        "audit_version": "1.1.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
