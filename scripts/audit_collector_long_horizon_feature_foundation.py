from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_long_horizon_feature_foundation/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = [
        "collector_long_horizon_source_catalog.csv",
        "collector_long_horizon_raw_field_coverage.csv",
        "collector_long_horizon_point_in_time_seed_panel.csv",
        "collector_long_horizon_derived_feature_plan.csv",
        "collector_long_horizon_feature_foundation_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists():
            failures.append(f"missing_output:{name}")

    if not failures:
        summary = json.loads((OUT / "collector_long_horizon_feature_foundation_summary.json").read_text(encoding="utf-8"))
        catalog = pd.read_csv(OUT / "collector_long_horizon_source_catalog.csv", low_memory=False)
        fields = pd.read_csv(OUT / "collector_long_horizon_raw_field_coverage.csv", low_memory=False)
        seed = pd.read_csv(OUT / "collector_long_horizon_point_in_time_seed_panel.csv", low_memory=False)
        features = pd.read_csv(OUT / "collector_long_horizon_derived_feature_plan.csv", low_memory=False)

        if summary.get("status") != "PASS":
            failures.append("builder_status_not_pass")
        if catalog.empty:
            failures.append("source_catalog_empty")
        if fields.empty:
            failures.append("raw_field_coverage_empty")
        if seed.empty:
            failures.append("seed_panel_empty")
        if features.empty:
            failures.append("derived_feature_plan_empty")
        if not seed.empty:
            if seed["future_information_used"].astype(str).str.lower().eq("true").any():
                failures.append("future_information_used")
            if not seed["outcome_separated_from_predictors"].astype(str).str.lower().eq("true").all():
                failures.append("outcome_not_separated_from_predictors")
            if "outcome_realized_return" not in seed.columns:
                failures.append("outcome_column_not_explicit")
        if not features.empty:
            if features["implemented"].astype(str).str.lower().eq("true").any():
                failures.append("unimplemented_features_marked_implemented")
            if features["certified"].astype(str).str.lower().eq("true").any():
                failures.append("unimplemented_features_marked_certified")
        for key in [
            "candidate_methodology_change_authorized",
            "production_projection_authorized",
            "purchase_recommendation_authorized",
            "automatic_model_update_allowed",
            "technical_freeze_authorized",
            "uip_acceptance_authorized",
        ]:
            if summary.get(key) is not False:
                failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector Long-Horizon Feature Foundation Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
