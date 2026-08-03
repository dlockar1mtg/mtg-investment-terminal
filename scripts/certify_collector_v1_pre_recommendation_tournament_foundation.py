from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_pre_recommendation_tournament_foundation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_pre_recommendation_tournament_foundation_summary.json"
    inventory_path = OUT_DIR / "collector_v1_pre_recommendation_authority_inventory.csv"
    matrix_path = OUT_DIR / "collector_v1_pre_recommendation_tournament_matrix.csv"

    failures: list[dict] = []
    if not summary_path.exists() or not inventory_path.exists() or not matrix_path.exists():
        failures.append({"check": "required foundation outputs exist", "severity": "CRITICAL"})
        summary = {}
        inventory = pd.DataFrame()
        matrix = pd.DataFrame()
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        inventory = pd.read_csv(inventory_path)
        matrix = pd.read_csv(matrix_path)

    checks = [
        ("all authorities resolved", not inventory.empty and bool(inventory["exists"].astype(str).str.lower().eq("true").all()), f"resolved={int(inventory['exists'].astype(str).str.lower().eq('true').sum()) if not inventory.empty else 0}"),
        ("winner manifest has 13 resolved cells", int(summary.get("short_horizon_manifest_rows", 0)) == 13, f"rows={summary.get('short_horizon_manifest_rows')}"),
        ("at least three resolved routes", len(summary.get("resolved_routes", [])) >= 3, f"routes={summary.get('resolved_routes')}"),
        ("six residual methods registered", len(summary.get("residual_methods", [])) == 6, f"count={len(summary.get('residual_methods', []))}"),
        ("two interval levels registered", summary.get("interval_levels") == [0.8, 0.9], f"levels={summary.get('interval_levels')}"),
        ("seven simulation methods registered", len(summary.get("simulation_methods", [])) == 7, f"count={len(summary.get('simulation_methods', []))}"),
        ("three-year and five-year horizons registered", summary.get("long_horizon_days") == [1095, 1825], f"horizons={summary.get('long_horizon_days')}"),
        ("five stress scenarios registered", len(summary.get("stress_scenarios", [])) == 5, f"count={len(summary.get('stress_scenarios', []))}"),
        ("minimum simulation count is 10000", int(summary.get("minimum_simulations_per_product_horizon", 0)) >= 10000, f"value={summary.get('minimum_simulations_per_product_horizon')}"),
        ("tournament matrix populated", len(matrix) >= 82, f"rows={len(matrix)}"),
        ("foundation ready", summary.get("foundation_ready") is True, f"value={summary.get('foundation_ready')}"),
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}"),
        ("recommendations remain blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}"),
    ]

    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Pre-Recommendation Tournament Foundation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "pre_recommendation_tournament_foundation_certified": certified,
        "residual_interval_tournament_authorized": certified,
        "long_horizon_simulation_tournament_authorized_after_residual_certification": certified,
        "decision_readiness_tournament_required": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Run residual and interval calibration tournament across certified routes" if certified else "Resolve missing or inconsistent tournament authorities",
        "status": "PASS_COLLECTOR_V1_PRE_RECOMMENDATION_TOURNAMENT_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_PRE_RECOMMENDATION_TOURNAMENT_FOUNDATION_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_pre_recommendation_tournament_foundation_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
