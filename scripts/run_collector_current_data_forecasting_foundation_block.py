"""Run the existing Collector forecasting foundation without continuity prerequisites."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_current_data_forecasting_foundation"
READINESS = ROOT / "data/governance/permanence/certification/collector_current_data_forecast_readiness/collector_current_data_forecast_readiness_summary.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run current-data Collector forecasting foundation")
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str], env: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return {"command": command, "return_code": result.returncode, "passed": result.returncode == 0}


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    steps: list[dict[str, object]] = []

    commands = [
        [sys.executable, "scripts/audit_collector_evidence_readiness.py"],
        [sys.executable, "scripts/normalize_collector_evidence.py"],
        [sys.executable, "scripts/route_collector_forecast_methods.py"],
        [sys.executable, "scripts/select_collector_comparables.py"],
        [sys.executable, "scripts/certify_collector_current_data_forecast_readiness.py"],
    ]
    for command in commands:
        steps.append(run(command, env))

    readiness = json.loads(READINESS.read_text(encoding="utf-8")) if READINESS.is_file() else {}
    authorized = readiness.get("forecast_experiment_authorized") is True
    implementation_passed = all(bool(step["passed"]) for step in steps[:-1])
    passed = authorized and implementation_passed
    summary = {
        "block_name": "Collector Current-Data Forecasting Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "continuity_dependency_removed": True,
        "existing_forecasting_foundation_executed": implementation_passed,
        "forecast_experiment_authorized": authorized,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": (
            "Build the governed current-data feature matrix and forecast experiment dataset"
            if passed
            else "Inspect current evidence discovery or existing forecasting foundation failures"
        ),
        "status": (
            "PASS_CURRENT_DATA_FORECASTING_FOUNDATION_READY"
            if passed else "REVIEW_CURRENT_DATA_FORECASTING_FOUNDATION"
        ),
    }
    (OUT / "collector_current_data_forecasting_foundation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
