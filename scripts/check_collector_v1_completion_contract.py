"""Evaluate the fail-closed Collector V1 completion contract.

This script does not discover authoritative inputs. It reads the governed
completion contract and the known certification outputs. Missing or failing
certifications keep downstream authorizations false.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/governance/collector_v1_completion_contract.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_completion_contract"

CERTIFICATIONS = {
    "authoritative_dependency_registry": (
        ROOT / "data/governance/permanence/certification/collector_v1_authoritative_data_registry/collector_v1_authoritative_data_registry_certification.json",
        "PASS_COLLECTOR_V1_AUTHORITATIVE_DATA_REGISTRY_CERTIFIED",
    ),
    "authoritative_feature_rebuild": (
        ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_matrix/collector_v1_authoritative_feature_matrix_certification.json",
        "PASS_COLLECTOR_V1_AUTHORITATIVE_FEATURE_MATRIX_CERTIFIED",
    ),
    "source_to_feature_lineage": (
        ROOT / "data/governance/permanence/certification/collector_v1_feature_lineage/collector_v1_feature_lineage_certification.json",
        "PASS_COLLECTOR_V1_FEATURE_LINEAGE_CERTIFIED",
    ),
    "data_sufficiency": (
        ROOT / "data/governance/permanence/certification/collector_v1_forecast_data_readiness/collector_v1_forecast_data_readiness_certification.json",
        "PASS_COLLECTOR_V1_FORECAST_DATA_READY",
    ),
    "cutoff_experiment_datasets": (
        ROOT / "data/governance/permanence/certification/collector_v1_experiment_dataset/collector_v1_experiment_dataset_certification.json",
        "PASS_COLLECTOR_V1_EXPERIMENT_DATASET_CERTIFIED",
    ),
    "historical_backtesting": (
        ROOT / "data/governance/permanence/certification/collector_v1_backtesting/collector_v1_backtesting_certification.json",
        "PASS_COLLECTOR_V1_BACKTESTING_CERTIFIED",
    ),
    "scarcity_ablation": (
        ROOT / "data/governance/permanence/certification/collector_v1_scarcity_ablation/collector_v1_scarcity_ablation_certification.json",
        "PASS_COLLECTOR_V1_SCARCITY_ABLATION_CERTIFIED",
    ),
    "uncertainty_calibration": (
        ROOT / "data/governance/permanence/certification/collector_v1_uncertainty_calibration/collector_v1_uncertainty_calibration_certification.json",
        "PASS_COLLECTOR_V1_UNCERTAINTY_CALIBRATION_CERTIFIED",
    ),
    "model_selection": (
        ROOT / "data/governance/permanence/certification/collector_v1_model_selection/collector_v1_model_selection_certification.json",
        "PASS_COLLECTOR_V1_MODEL_SELECTION_CERTIFIED",
    ),
    "current_forecast_tables": (
        ROOT / "data/governance/permanence/certification/collector_v1_current_forecasts/collector_v1_current_forecasts_certification.json",
        "PASS_COLLECTOR_V1_CURRENT_FORECASTS_CERTIFIED",
    ),
    "purchase_eligibility": (
        ROOT / "data/governance/permanence/certification/collector_v1_purchase_eligibility/collector_v1_purchase_eligibility_certification.json",
        "PASS_COLLECTOR_V1_PURCHASE_ELIGIBILITY_CERTIFIED",
    ),
    "uip_export": (
        ROOT / "data/governance/permanence/certification/collector_v1_uip_export/collector_v1_uip_export_certification.json",
        "PASS_COLLECTOR_V1_UIP_EXPORT_CERTIFIED",
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    contract = load_json(CONTRACT)
    gate_results: list[dict[str, Any]] = []

    for gate, (path, expected_status) in CERTIFICATIONS.items():
        exists = path.is_file()
        actual_status = ""
        passed = False
        error = ""
        if exists:
            try:
                payload = load_json(path)
                actual_status = str(payload.get("status", ""))
                passed = actual_status == expected_status
            except Exception as exc:  # fail closed
                error = f"{type(exc).__name__}: {exc}"
        gate_results.append(
            {
                "gate": gate,
                "certification_path": path.relative_to(ROOT).as_posix(),
                "exists": exists,
                "expected_status": expected_status,
                "actual_status": actual_status,
                "passed": passed,
                "error": error,
            }
        )

    failed = [row for row in gate_results if not row["passed"]]
    all_passed = not failed
    summary = {
        "block_name": "Collector V1 Completion Contract Gate",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_path": CONTRACT.relative_to(ROOT).as_posix(),
        "fail_closed": bool(contract.get("fail_closed", True)),
        "total_gates": len(gate_results),
        "passed_gates": sum(1 for row in gate_results if row["passed"]),
        "failed_gates": failed,
        "collector_v1_complete": all_passed,
        "forecast_experiments_authorized": all_passed,
        "production_forecasting_authorized": all_passed,
        "purchase_recommendations_authorized": all_passed,
        "uip_delivery_authorized": all_passed,
        "status": (
            "PASS_COLLECTOR_V1_COMPLETION_CONTRACT"
            if all_passed
            else "BLOCKED_COLLECTOR_V1_COMPLETION_GATES_OUTSTANDING"
        ),
    }

    (OUT / "collector_v1_completion_contract_gate_results.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if all_passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
