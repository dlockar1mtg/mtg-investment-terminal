from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_long_horizon_evidence_inventory/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = [
        "collector_long_horizon_direct_evidence.csv",
        "collector_long_horizon_component_inventory.csv",
        "collector_long_horizon_standards_coverage.csv",
        "collector_long_horizon_class_transfer_plan.csv",
        "collector_long_horizon_evidence_inventory_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists():
            failures.append(f"missing_output:{name}")

    if not failures:
        summary = json.loads((OUT / required[-1]).read_text(encoding="utf-8"))
        components = pd.read_csv(OUT / required[1], low_memory=False)
        standards = pd.read_csv(OUT / required[2], low_memory=False)
        transfer = pd.read_csv(OUT / required[3], low_memory=False)
        if summary.get("status") != "PASS": failures.append("builder_status_not_pass")
        if components.empty: failures.append("component_inventory_empty")
        if standards.empty: failures.append("standards_coverage_empty")
        if transfer.empty: failures.append("transfer_plan_empty")
        expected_horizons = {"365_day", "3_year", "5_year"}
        if set(components["horizon"].astype(str)) != expected_horizons:
            failures.append("component_horizon_coverage_incomplete")
        if set(standards["horizon"].astype(str)) != expected_horizons:
            failures.append("standards_horizon_coverage_incomplete")
        expected_classes = {"PRE_COLLECTOR", "SECRET_LAIR"}
        if set(transfer["asset_class"].astype(str)) != expected_classes:
            failures.append("class_transfer_coverage_incomplete")
        for key in [
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
        "audit_name": "Collector Long-Horizon Evidence Inventory Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
