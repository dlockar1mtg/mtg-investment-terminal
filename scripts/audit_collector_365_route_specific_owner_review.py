from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_365_route_specific_owner_review/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    summary_path = OUT / "collector_365_route_specific_owner_review_summary.json"
    review_path = OUT / "collector_365_route_specific_owner_review.csv"
    if not summary_path.exists():
        failures.append("summary_missing")
    if not review_path.exists():
        failures.append("review_missing")

    summary = {}
    review = pd.DataFrame()
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append("summary_unreadable")
    if review_path.exists():
        try:
            review = pd.read_csv(review_path, low_memory=False)
        except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
            failures.append("review_unreadable")

    if review.empty:
        failures.append("review_empty")
    else:
        required = {
            "product_age_route", "recommended_method", "bias_shrinkage", "evidence_grade",
            "owner_review_eligible", "shadow_implementation_authorized",
        }
        if not required.issubset(review.columns):
            failures.append("review_contract_incomplete")
        expected = {"MATURE": "DIRECT", "DEVELOPING": "COMPARABLE", "LIMITED": "BLOCKED"}
        actual = dict(zip(review["product_age_route"].astype(str), review["recommended_method"].astype(str)))
        if actual != expected:
            failures.append("route_recommendation_mismatch")
        authorized = review["shadow_implementation_authorized"].astype(str).str.lower().eq("true")
        if authorized.any():
            failures.append("shadow_implementation_prematurely_authorized")

    for key in [
        "route_specific_shadow_implementation_authorized",
        "direct_method_authorized",
        "comparable_transfer_method_authorized",
        "limited_route_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
        "technical_freeze_authorized",
        "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")
    if summary.get("owner_approval_required") is not True:
        failures.append("owner_approval_gate_missing")

    result = {
        "audit_name": "Collector 365-Day Route-Specific Owner Review Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
