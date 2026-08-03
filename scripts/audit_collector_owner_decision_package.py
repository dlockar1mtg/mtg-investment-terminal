from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "config/mtg/governance/collector_numeric_methodology_owner_decision_v1.json"
ALLOWED_STATUS = {"PROPOSED_INACTIVE"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(payload: dict) -> dict:
    failures: list[str] = []
    groups = payload.get("decision_groups", [])

    if payload.get("status") not in ALLOWED_STATUS:
        failures.append("PACKAGE_STATUS_NOT_PROPOSED_INACTIVE")
    if payload.get("methodology_activated") is not False:
        failures.append("METHODOLOGY_MUST_REMAIN_INACTIVE")
    if payload.get("projection_authorized") is not False:
        failures.append("PROJECTION_MUST_REMAIN_UNAUTHORIZED")
    if payload.get("purchase_recommendation_authorized") is not False:
        failures.append("PURCHASE_RECOMMENDATION_MUST_REMAIN_UNAUTHORIZED")
    if not groups:
        failures.append("NO_DECISION_GROUPS")

    ids: list[str] = []
    for group in groups:
        decision_id = str(group.get("decision_id", "")).strip()
        ids.append(decision_id)
        options = group.get("options", [])
        option_ids = {str(option.get("option_id", "")).strip() for option in options}
        recommended = str(group.get("recommended_option", "")).strip()

        if not decision_id:
            failures.append("MISSING_DECISION_ID")
        if len(options) < 2:
            failures.append(f"{decision_id}:INSUFFICIENT_OPTIONS")
        if recommended not in option_ids:
            failures.append(f"{decision_id}:INVALID_RECOMMENDATION")
        if group.get("owner_selection") is not None:
            failures.append(f"{decision_id}:OWNER_SELECTION_PREPOPULATED")
        if group.get("owner_notes") is not None:
            failures.append(f"{decision_id}:OWNER_NOTES_PREPOPULATED")

    duplicates = [key for key, count in Counter(ids).items() if key and count > 1]
    failures.extend(f"DUPLICATE_DECISION_ID:{key}" for key in duplicates)

    return {
        "audit_name": "Collector Owner Decision Package Audit",
        "audit_version": "1.0.0",
        "decision_group_count": len(groups),
        "methodology_changed": False,
        "methodology_activated": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
        "governing_note": "This audit validates proposal completeness and inactivity only. It does not record owner approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the inactive Collector owner decision package.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary = audit(load_json(args.input))
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.strict and summary["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
