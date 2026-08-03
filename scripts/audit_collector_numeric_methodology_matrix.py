from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "collector_numeric_methodology_matrix_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "collector_numeric_methodology"
    / "candidate_v1_0_0"
)

ALLOWED_AUTHORITY = {
    "FULLY_DEFINED_BY_STANDARD",
    "PARTIALLY_DEFINED_BY_STANDARD",
    "OWNER_APPROVED",
    "NOT_DEFINED_OWNER_DECISION_REQUIRED",
    "NON_METHODOLOGICAL",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Collector numeric methodology authority without activating methodology."
    )
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    matrix = read_json(args.matrix)
    requirements = matrix.get("requirements", [])
    failures: list[str] = []
    decisions: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    seen_ids: set[str] = set()
    for row in requirements:
        requirement_id = str(row.get("requirement_id", "")).strip()
        authority = str(row.get("authority_status", "")).strip()
        implementation_state = str(row.get("implementation_state", "")).strip()

        if not requirement_id:
            failures.append("MISSING_REQUIREMENT_ID")
        elif requirement_id in seen_ids:
            failures.append(f"DUPLICATE_REQUIREMENT_ID:{requirement_id}")
        seen_ids.add(requirement_id)

        if authority not in ALLOWED_AUTHORITY:
            failures.append(f"INVALID_AUTHORITY_STATUS:{requirement_id}:{authority}")
        status_counts[authority] += 1

        if authority in {
            "NOT_DEFINED_OWNER_DECISION_REQUIRED",
            "PARTIALLY_DEFINED_BY_STANDARD",
        }:
            decisions.append(
                {
                    "requirement_id": requirement_id,
                    "requirement": row.get("requirement", ""),
                    "authority_status": authority,
                    "source": row.get("source", ""),
                    "implementation_state": implementation_state,
                }
            )
            if implementation_state == "ACTIVE":
                failures.append(f"UNAPPROVED_METHODOLOGY_ACTIVE:{requirement_id}")

    if matrix.get("methodology_changed") is not False:
        failures.append("METHODOLOGY_CHANGED_MUST_REMAIN_FALSE")
    if matrix.get("projection_authorized") is not False:
        failures.append("PROJECTION_AUTHORIZATION_MUST_REMAIN_FALSE")
    if matrix.get("purchase_recommendation_authorized") is not False:
        failures.append("PURCHASE_AUTHORIZATION_MUST_REMAIN_FALSE")

    args.output.mkdir(parents=True, exist_ok=True)
    write_json(
        args.output / "collector_owner_decision_requirements.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "decision_count": len(decisions),
            "decisions": decisions,
            "governing_note": (
                "These are methodology gaps or partial definitions. No listed behavior is "
                "authorized for production until the standard defines it or the owner approves it."
            ),
        },
    )

    summary = {
        "audit_name": "Collector Numeric Methodology Authority Audit",
        "audit_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requirement_count": len(requirements),
        "authority_distribution": dict(sorted(status_counts.items())),
        "owner_decision_requirement_count": len(decisions),
        "failure_count": len(failures),
        "failures": sorted(failures),
        "methodology_changed": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "owner_approval_status": "NOT_REQUESTED",
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
    }
    write_json(args.output / "collector_numeric_methodology_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
