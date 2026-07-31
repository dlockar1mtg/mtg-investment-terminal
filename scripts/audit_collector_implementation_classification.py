from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFICATION = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "collector_implementation_classification_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "collector_forecast_traceability"
    / "classification_v1_0_0"
)

ALLOWED_CLASSIFICATIONS = {
    "ACTIVE_STANDARD_AUTHORIZED",
    "ACTIVE_OWNER_APPROVED",
    "SUPPORTING_NON_METHODOLOGICAL",
    "HISTORICAL_REFERENCE",
    "SUPERSEDED_REFERENCE",
    "CONFLICTING_IMPLEMENTATION",
    "OWNER_APPROVAL_REQUIRED",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Collector implementation classifications without changing methodology."
    )
    parser.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    payload = read_json(args.classification)
    rows = payload.get("classifications", [])
    failures: list[str] = []
    counts: Counter[str] = Counter()

    for row in rows:
        path_text = str(row.get("path") or "").strip()
        classification = str(row.get("classification") or "").strip()
        reason = str(row.get("reason") or "").strip()

        if not path_text:
            failures.append("MISSING_PATH")
            continue
        if classification not in ALLOWED_CLASSIFICATIONS:
            failures.append(f"{path_text}:INVALID_CLASSIFICATION:{classification}")
        if not reason:
            failures.append(f"{path_text}:MISSING_REASON")
        if not (ROOT / path_text).exists():
            failures.append(f"{path_text}:MISSING_SOURCE")
        counts[classification] += 1

    if payload.get("methodology_changed") is not False:
        failures.append("METHODOLOGY_CHANGED_MUST_REMAIN_FALSE")
    if payload.get("projection_authorized") is not False:
        failures.append("PROJECTION_AUTHORIZATION_MUST_REMAIN_FALSE")
    if payload.get("purchase_recommendation_authorized") is not False:
        failures.append("PURCHASE_AUTHORIZATION_MUST_REMAIN_FALSE")

    active_authoritative = {
        row.get("path")
        for row in rows
        if row.get("classification")
        in {"ACTIVE_STANDARD_AUTHORIZED", "ACTIVE_OWNER_APPROVED"}
    }
    required_active = {
        "scripts/route_collector_forecast_methods.py",
        "scripts/normalize_collector_evidence.py",
        "scripts/select_collector_comparables.py",
        "data/governance/mtg/collector_comparables/collector_japanese_edition_hybrid_override_v1.json",
    }
    for missing in sorted(required_active - active_authoritative):
        failures.append(f"{missing}:REQUIRED_ACTIVE_CLASSIFICATION_MISSING")

    summary = {
        "audit_name": "Collector Implementation Classification Audit",
        "audit_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification_count": len(rows),
        "classification_distribution": dict(sorted(counts.items())),
        "failure_count": len(failures),
        "failures": sorted(failures),
        "methodology_changed": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "owner_approval_status": payload.get("owner_approval_status", "NOT_REQUESTED"),
        "status": "PASS" if not failures else "REVIEW_REQUIRED",
        "governing_note": (
            "This audit validates classification and preservation only. It does not approve "
            "or activate forecast methodology."
        ),
    }
    write_json(args.output / "collector_implementation_classification_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
