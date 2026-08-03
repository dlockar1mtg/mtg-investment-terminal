from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_4_confidence_decision_owner_review/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures = []
    required = [
        "collector_candidate_v2_4_confidence_owner_review.csv",
        "collector_candidate_v2_4_decision_owner_review.csv",
        "collector_candidate_v2_4_confidence_decision_owner_review_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists():
            failures.append(f"missing_output:{name}")
    if not failures:
        summary = json.loads((OUT / required[2]).read_text(encoding="utf-8"))
        confidence = pd.read_csv(OUT / required[0], low_memory=False)
        decisions = pd.read_csv(OUT / required[1], low_memory=False)
        if summary.get("status") != "PASS": failures.append("finalizer_status_not_pass")
        if confidence.empty: failures.append("confidence_review_empty")
        if decisions.empty: failures.append("decision_review_empty")
        if confidence["confidence_authorized"].astype(str).str.lower().eq("true").any():
            failures.append("confidence_unauthorized_open")
        if decisions["decision_method_authorized"].astype(str).str.lower().eq("true").any():
            failures.append("decision_unauthorized_open")
        for key in [
            "prospective_confidence_method_authorized",
            "decision_state_method_authorized",
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
        "audit_name": "Collector Candidate v2.4 Confidence and Decision Owner Review Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
