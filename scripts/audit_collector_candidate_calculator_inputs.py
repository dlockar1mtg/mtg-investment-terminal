from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data" / "operations" / "collector_candidate_calculator" / "input_audit_v1_0_0"

DATASETS: dict[str, list[str]] = {
    "routes": [
        "data/operations/collector_forecast_method_routing/**/collector_forecast_method_routes.csv",
    ],
    "evidence": [
        "data/operations/collector_evidence_normalization/**/collector_normalized_evidence.csv",
        "data/operations/collector_evidence_normalization/**/normalized_collector_evidence.csv",
        "data/operations/**/collector_normalized_evidence.csv",
    ],
    "history": [
        "data/operations/collector_history_certification/**/collector_history_certification.csv",
        "data/operations/**/collector_history*.csv",
    ],
    "selected_comparables": [
        "data/operations/collector_comparable_selection/**/collector_selected_comparables.csv",
        "data/operations/**/collector_selected_comparables.csv",
    ],
    "comparable_targets": [
        "data/operations/collector_comparable_selection/**/collector_comparable_target_status.csv",
        "data/operations/**/collector_comparable_target_status.csv",
    ],
    "numeric_candidate": [
        "config/mtg/governance/collector_numeric_specification_candidate_v1.json",
    ],
    "owner_approval": [
        "config/mtg/governance/collector_numeric_methodology_owner_approval_v1.json",
    ],
}

REQUIRED_DATASETS = {
    "routes",
    "evidence",
    "history",
    "selected_comparables",
    "numeric_candidate",
    "owner_approval",
}


def discover(patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        if "**" in pattern or "*" in pattern:
            found.extend(ROOT.glob(pattern))
        else:
            path = ROOT / pattern
            if path.exists():
                found.append(path)
    return sorted({path.resolve() for path in found if path.is_file()})


def csv_profile(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        row_count = sum(1 for _ in reader)
    return {"columns": fields, "column_count": len(fields), "row_count": row_count}


def json_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "json_type": type(payload).__name__,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover and profile the current inputs for the inactive Collector candidate calculator."
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    missing_required: list[str] = []

    for dataset, patterns in DATASETS.items():
        matches = discover(patterns)
        if dataset in REQUIRED_DATASETS and not matches:
            missing_required.append(dataset)
        for path in matches:
            profile = csv_profile(path) if path.suffix.lower() == ".csv" else json_profile(path)
            records.append(
                {
                    "dataset": dataset,
                    "path": str(path.relative_to(ROOT)),
                    "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "size_bytes": path.stat().st_size,
                    **profile,
                }
            )

    inventory_path = OUTPUT_ROOT / "collector_candidate_input_inventory.json"
    inventory_path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "audit_name": "Collector Candidate Calculator Input Audit",
        "audit_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_match_count": len(records),
        "discovered_dataset_types": sorted({record["dataset"] for record in records}),
        "missing_required_dataset_count": len(missing_required),
        "missing_required_datasets": missing_required,
        "methodology_changed": False,
        "methodology_activated": False,
        "projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "status": "PASS" if not missing_required else "REVIEW_REQUIRED",
        "governing_note": (
            "This audit discovers current local inputs and schemas only. It does not calculate, approve, "
            "or activate forecasts."
        ),
    }
    summary_path = OUTPUT_ROOT / "collector_candidate_input_audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and missing_required:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
