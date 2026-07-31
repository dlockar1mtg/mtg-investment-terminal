from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_PATH = ROOT / "config/mtg/governance/collector_numeric_methodology_owner_approval_v1.json"
OUTPUT_PATH = ROOT / "data/operations/collector_numeric_methodology/owner_approval_v1_0_0/collector_numeric_methodology_owner_approval_summary.json"

EXPECTED_DECISIONS = {f"COL-DEC-{index:03d}" for index in range(1, 8)}
ALLOWED_APPROVAL_STATUSES = {"APPROVED", "APPROVED_WITH_CONDITION", "APPROVED_WITH_CONDITIONS"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Collector conceptual numeric methodology owner approval.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    approvals = payload.get("approvals", [])
    failures: list[str] = []

    decision_ids = [str(row.get("decision_id", "")) for row in approvals]
    if set(decision_ids) != EXPECTED_DECISIONS:
        failures.append("APPROVAL_DECISION_SET_MISMATCH")
    if len(decision_ids) != len(set(decision_ids)):
        failures.append("DUPLICATE_DECISION_APPROVAL")

    for row in approvals:
        decision_id = str(row.get("decision_id", ""))
        if row.get("owner_selection") != "A":
            failures.append(f"{decision_id}:UNEXPECTED_OWNER_SELECTION")
        if row.get("approval_status") not in ALLOWED_APPROVAL_STATUSES:
            failures.append(f"{decision_id}:INVALID_APPROVAL_STATUS")
        if not row.get("approved_concept"):
            failures.append(f"{decision_id}:MISSING_APPROVED_CONCEPT")
        if not row.get("conditions"):
            failures.append(f"{decision_id}:MISSING_APPROVAL_CONDITIONS")

    for forbidden_true_field in (
        "methodology_activated",
        "projection_authorized",
        "purchase_recommendation_authorized",
        "exact_numeric_specification_approved",
    ):
        if payload.get(forbidden_true_field) is not False:
            failures.append(f"{forbidden_true_field}:MUST_REMAIN_FALSE")

    if "Hard forecast caps" not in payload.get("not_authorized", []):
        failures.append("HARD_CAPS_NOT_EXPLICITLY_PROHIBITED")
    if "Automatic disqualification based only on insufficient mature history" not in payload.get("not_authorized", []):
        failures.append("EARLY_OPPORTUNITY_PROTECTION_MISSING")

    summary = {
        "audit_name": "Collector Numeric Methodology Owner Approval Audit",
        "audit_version": "1.0.0",
        "approval_count": len(approvals),
        "approval_status_distribution": dict(sorted(Counter(row.get("approval_status", "") for row in approvals).items())),
        "failure_count": len(failures),
        "failures": failures,
        "conceptual_methodology_approved": not failures,
        "exact_numeric_specification_approved": payload.get("exact_numeric_specification_approved", False),
        "methodology_activated": payload.get("methodology_activated", False),
        "projection_authorized": payload.get("projection_authorized", False),
        "purchase_recommendation_authorized": payload.get("purchase_recommendation_authorized", False),
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
        "governing_note": "Concept approval authorizes detailed specification and candidate backtesting only; it does not authorize production forecasts or purchases.",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
