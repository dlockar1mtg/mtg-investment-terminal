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
        if results["horizon_days"].nunique() != 3:
            failures.append("horizon_count_not_3")
        if results["robustness_test"].nunique() != 5:
            failures.append("robustness_test_count_not_5")
        if len(results) != 15:
            failures.append("robustness_result_count_not_15")
        if len(horizon) != 3:
            failures.append("horizon_summary_count_not_3")
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
