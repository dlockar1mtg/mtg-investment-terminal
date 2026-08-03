from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_methodology_decision_capture/candidate_v1_0_0"
SUMMARY = OUT / "collector_methodology_decision_capture_summary.json"
RECON = OUT / "collector_comparable_baseline_adjustment_reconciliation.csv"
BALLOT = OUT / "collector_methodology_owner_decision_ballot.csv"
SPEC = OUT / "collector_methodology_decision_capture_specification.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    for path in [SUMMARY, RECON, BALLOT, SPEC]:
        if not path.exists():
            failures.append(f"missing_output:{path}")

    if failures:
        print(json.dumps({"status": "FAIL", "failure_count": len(failures), "failures": failures}, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    recon = pd.read_csv(RECON, low_memory=False)
    ballot = pd.read_csv(BALLOT, low_memory=False)
    spec = json.loads(SPEC.read_text(encoding="utf-8"))

    if int(summary.get("product_count", 0)) != 51:
        failures.append("product_count_expected_51")
    if len(recon) != 24:
        failures.append(f"comparable_reconciliation_expected_24_actual_{len(recon)}")
    if len(ballot) != 6:
        failures.append(f"decision_count_expected_6_actual_{len(ballot)}")
    if not (recon["adjustment_basis_status"].astype(str) == "UNRESOLVED_SOURCE_DOCUMENTATION_REQUIRED").all():
        failures.append("unresolved_adjustment_status_violation")
    if recon["adjustment_authorized"].astype(str).str.lower().isin(["true", "1", "yes"]).any():
        failures.append("adjustment_unexpectedly_authorized")
    if spec.get("baseline_adjustment_reconciled") is not False:
        failures.append("baseline_adjustment_unexpectedly_reconciled")
    for key in ["candidate_projection_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
        if bool(spec.get(key)) or bool(summary.get(key)):
            failures.append(f"{key}_unexpectedly_true")

    result = {
        "audit_name": "Collector Methodology Decision Capture Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(summary.get("product_count", 0)),
        "comparable_product_count": int(len(recon)),
        "decision_count": int(len(ballot)),
        "pending_owner_decision_count": int(summary.get("pending_owner_decision_count", 0)),
        "baseline_adjustment_reconciled": False,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit verifies that unresolved adjustments remain unnamed and unauthorized and that all six decisions remain explicit."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
