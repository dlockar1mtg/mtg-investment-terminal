"""Certify that the remaining Collector downstream pipeline is implemented and gated."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_remaining_pipeline_readiness"

REQUIRED_SCRIPTS = [
    ROOT / "scripts/run_collector_ebay_first_continuity_acquisition_block.py",
    ROOT / "scripts/build_collector_ebay_continuity_comparison.py",
    ROOT / "scripts/certify_collector_supply_scarcity_feature_readiness.py",
    ROOT / "scripts/certify_collector_forecast_and_purchase_readiness.py",
]


def run(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT, check=False)
    return {"command": command, "return_code": result.returncode, "passed": result.returncode == 0}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_SCRIPTS if not path.is_file()]
    steps: list[dict[str, object]] = []
    if not missing:
        steps.append(run([sys.executable, "scripts/certify_collector_supply_scarcity_feature_readiness.py", "--strict"]))
        steps.append(run([sys.executable, "scripts/certify_collector_forecast_and_purchase_readiness.py", "--strict"]))

    scarcity_path = ROOT / "data/governance/permanence/certification/collector_supply_scarcity_feature_readiness/collector_supply_scarcity_feature_readiness_summary.json"
    forecast_path = ROOT / "data/governance/permanence/certification/collector_forecast_and_purchase_readiness/collector_forecast_and_purchase_readiness_summary.json"
    scarcity = json.loads(scarcity_path.read_text(encoding="utf-8")) if scarcity_path.is_file() else {}
    forecast = json.loads(forecast_path.read_text(encoding="utf-8")) if forecast_path.is_file() else {}

    implementation_ready = not missing and all(step["passed"] for step in steps)
    gates_fail_closed = (
        scarcity.get("feature_calculation_authorized") is not True
        and forecast.get("production_forecasting_authorized") is not True
        and forecast.get("purchase_recommendations_authorized") is not True
        and forecast.get("uip_delivery_authorized") is not True
    )
    passed = implementation_ready and gates_fail_closed
    summary = {
        "block_name": "Collector Remaining Pipeline Readiness",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "required_scripts": [str(p.relative_to(ROOT)) for p in REQUIRED_SCRIPTS],
        "missing_scripts": missing,
        "steps": steps,
        "downstream_implementation_ready": implementation_ready,
        "fail_closed_authorization_verified": gates_fail_closed,
        "data_state": {
            "day_one_baseline": "PROMOTED",
            "first_continuity_observation": "PENDING_INTERVAL_AND_LIVE_COLLECTION",
            "continuity_comparison": "IMPLEMENTED_AWAITING_CERTIFIED_CURRENT_OBSERVATION",
            "scarcity_feature_readiness": scarcity.get("status", "NOT_RUN"),
            "forecast_and_purchase_readiness": forecast.get("status", "NOT_RUN"),
        },
        "authorization_state": {
            "continuity_acquisition": "TIME_GATED",
            "continuity_comparison": "READY_ON_CERTIFIED_INPUT",
            "supply_scarcity_index_v1": "BLOCKED_PENDING_MINIMUM_HISTORY",
            "forecast_experiments": "BLOCKED_PENDING_SCARCITY_FEATURES",
            "production_forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "remaining_external_dependencies": [
            "At least one eligible post-baseline eBay acquisition",
            "Hardened and adjudicated current-observation ledgers",
            "Minimum certified observation history for scarcity features",
            "Forecast experiment, backtest, calibration, and production approval",
        ],
        "status": (
            "PASS_COLLECTOR_DOWNSTREAM_IMPLEMENTATION_READY_DATA_PENDING"
            if passed else "FAIL_COLLECTOR_DOWNSTREAM_IMPLEMENTATION_READINESS"
        ),
    }
    (OUT / "collector_remaining_pipeline_readiness_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
