from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_methodology_adjustment_trace_and_final_ballot/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "summary": OUT / "collector_methodology_adjustment_trace_and_final_ballot_summary.json",
        "trace": OUT / "collector_comparable_adjustment_trace.csv",
        "groups": OUT / "collector_comparable_adjustment_trace_groups.csv",
        "ballot": OUT / "collector_methodology_final_owner_ballot.csv",
        "spec": OUT / "collector_methodology_final_inactive_specification.json",
    }
    failures = [f"missing_output:{name}:{path}" for name, path in paths.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
    trace = pd.read_csv(paths["trace"], low_memory=False)
    ballot = pd.read_csv(paths["ballot"], low_memory=False)

    if int(summary.get("product_count", 0)) != 51:
        failures.append("product_count_expected_51")
    if len(trace) != 24:
        failures.append(f"comparable_product_count_expected_24_actual_{len(trace)}")
    if len(ballot) != 6:
        failures.append(f"decision_count_expected_6_actual_{len(ballot)}")
    if "fundamental_match_within_tolerance" not in trace.columns:
        failures.append("fundamental_match_column_missing")
    if "unexplained_residual_after_fundamental" not in trace.columns:
        failures.append("unexplained_residual_column_missing")
    if "adjustment_authorized" not in trace.columns or trace["adjustment_authorized"].astype(str).str.lower().isin({"true", "1", "yes"}).any():
        failures.append("adjustment_unexpectedly_authorized")
    if "activation_authorized" not in ballot.columns or ballot["activation_authorized"].astype(str).str.lower().isin({"true", "1", "yes"}).any():
        failures.append("methodology_unexpectedly_activated")
    for key in [
        "candidate_projection_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]:
        if bool(spec.get(key)):
            failures.append(f"{key}_unexpectedly_true")

    result = {
        "audit_name": "Collector Methodology Adjustment Trace and Final Ballot Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(summary.get("product_count", 0)),
        "comparable_product_count": int(len(trace)),
        "fundamental_match_count": int(summary.get("fundamental_match_count", 0)),
        "unexplained_residual_count": int(summary.get("unexplained_residual_count", 0)),
        "decision_count": int(len(ballot)),
        "pending_owner_decision_count": int(summary.get("pending_owner_decision_count", 0)),
        "baseline_adjustment_trace_complete": bool(summary.get("baseline_adjustment_trace_complete")),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit verifies adjustment traceability, explicit owner decisions, and closed authorization boundaries. It does not approve the methodology.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
