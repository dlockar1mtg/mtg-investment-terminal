from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_long_horizon_method_remediation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_targeted_long_horizon_method_remediation_summary.json"
    winners_path = OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv"
    failures: list[dict] = []

    if not summary_path.exists() or not winners_path.exists():
        summary = {}
        winners = pd.DataFrame()
        failures.append({"check": "required outputs exist", "severity": "CRITICAL"})
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        winners = pd.read_csv(winners_path)

    accepted = {"PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"}
    checks = [
        ("two direct routes targeted", len(summary.get("targeted_routes", [])) == 2, f"routes={summary.get('targeted_routes')}"),
        ("all four method routes present", len(winners) == 4, f"rows={len(winners)}"),
        ("no unresolved routes", int(summary.get("final_unresolved_routes", -1)) == 0, f"value={summary.get('final_unresolved_routes')}"),
        ("all route statuses accepted", bool(not winners.empty and winners["promotion_status"].isin(accepted).all()), f"statuses={winners.get('promotion_status', pd.Series(dtype=str)).tolist()}"),
        ("product holdout enforced", summary.get("product_holdout_enforced") is True, f"value={summary.get('product_holdout_enforced')}"),
        ("original gates unchanged", summary.get("original_coverage_and_tail_gates_unchanged") is True, f"value={summary.get('original_coverage_and_tail_gates_unchanged')}"),
        ("method stack complete", summary.get("long_horizon_method_stack_complete") is True, f"value={summary.get('long_horizon_method_stack_complete')}"),
        ("scenario rebuild authorized", summary.get("scenario_simulation_rebuild_authorized") is True, f"value={summary.get('scenario_simulation_rebuild_authorized')}"),
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}"),
        ("recommendations remain blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}"),
    ]
    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Targeted Long-Horizon Method Remediation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "targeted_long_horizon_method_remediation_certified": certified,
        "long_horizon_method_stack_certified": certified,
        "scenario_simulation_rebuild_authorized": certified,
        "decision_readiness_tournament_authorized_after_scenario_rebuild": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Rebuild 3-year and 5-year scenario distributions from certified final method winners" if certified else "Continue route-specific method remediation without lowering gates",
        "status": "PASS_COLLECTOR_V1_TARGETED_LONG_HORIZON_METHOD_REMEDIATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_TARGETED_LONG_HORIZON_METHOD_REMEDIATION_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_targeted_long_horizon_method_remediation_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
