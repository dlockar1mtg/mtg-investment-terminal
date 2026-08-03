from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2c_robustness/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = [
        OUT / "collector_walk_forward_phase_2c_robustness_results.csv",
        OUT / "collector_walk_forward_phase_2c_horizon_summary.csv",
        OUT / "collector_walk_forward_phase_2c_summary.json",
    ]
    for path in required:
        if not path.exists():
            failures.append(f"missing:{path.name}")

    if not failures:
        results = pd.read_csv(required[0])
        horizon = pd.read_csv(required[1])
        summary = json.loads(required[2].read_text(encoding="utf-8"))

        required_tests = {
            "ALL_CASES",
            "EXCLUDE_HIGHEST_ERROR_PRODUCT",
            "TRIM_TOP_5_PERCENT_CURRENT_MODEL_ERRORS",
            "EARLY_CUTOFF_HALF",
            "LATE_CUTOFF_HALF",
        }

        if results["horizon_days"].nunique() != 3:
            failures.append("horizon_count_not_3")
        if not required_tests.issubset(set(results["robustness_test"])):
            failures.append("missing_required_robustness_test")
        if results.duplicated(["robustness_test", "horizon_days"]).any():
            failures.append("duplicate_robustness_test_horizon")
        if len(horizon) != 3:
            failures.append("horizon_summary_count_not_3")

        expected_result_count = int(horizon["robustness_test_count"].sum()) if not horizon.empty else 0
        if len(results) != expected_result_count:
            failures.append("robustness_result_count_mismatch")
        if int(summary.get("robustness_result_count", -1)) != len(results):
            failures.append("summary_robustness_result_count_mismatch")

        all_cases_horizons = set(
            pd.to_numeric(
                results.loc[results["robustness_test"] == "ALL_CASES", "horizon_days"],
                errors="coerce",
            ).dropna().astype(int)
        )
        if all_cases_horizons != {90, 180, 365}:
            failures.append("all_cases_missing_required_horizon")

        for field in [
            "candidate_methodology_change_authorized",
            "production_projection_authorized",
            "purchase_recommendation_authorized",
            "automatic_model_update_allowed",
        ]:
            if summary.get(field) is not False:
                failures.append(f"authorization_not_closed:{field}")
        if summary.get("freeze_suspended_pending_walk_forward") is not True:
            failures.append("freeze_not_suspended")

    result = {
        "audit_name": "Collector Walk-Forward Phase 2C Robustness Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
