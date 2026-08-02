from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_interval_remediation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_targeted_interval_remediation_summary.json"
    winner_path = OUT_DIR / "collector_v1_targeted_interval_winner.csv"
    consolidated_path = OUT_DIR / "collector_v1_consolidated_residual_interval_winners.csv"
    failures: list[dict] = []

    if not summary_path.exists() or not winner_path.exists() or not consolidated_path.exists():
        failures.append({"check": "required outputs exist", "severity": "CRITICAL"})
        summary = {}
        winner = pd.DataFrame()
        consolidated = pd.DataFrame()
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        winner = pd.read_csv(winner_path)
        consolidated = pd.read_csv(consolidated_path)

    checks = [
        ("exactly one targeted winner exists", len(winner) == 1, f"rows={len(winner)}"),
        ("targeted cell resolved", summary.get("targeted_cell_resolved") is True, f"value={summary.get('targeted_cell_resolved')}"),
        ("targeted winner promoted", bool(not winner.empty and winner.iloc[0].get("promotion_status") == "PROMOTABLE"), f"status={winner.iloc[0].get('promotion_status') if not winner.empty else None}"),
        ("product holdout enforced", summary.get("product_holdout_enforced") is True, f"value={summary.get('product_holdout_enforced')}"),
        ("consolidated winner count remains 24", len(consolidated) == 24, f"rows={len(consolidated)}"),
        ("consolidated unresolved count is zero", summary.get("consolidated_unresolved_cells") == 0, f"value={summary.get('consolidated_unresolved_cells')}"),
        ("residual interval stack complete", summary.get("residual_interval_stack_complete") is True, f"value={summary.get('residual_interval_stack_complete')}"),
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}"),
        ("purchase recommendations remain blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}"),
    ]

    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Targeted Interval Remediation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "targeted_interval_remediation_certified": certified,
        "residual_interval_stack_certified": certified,
        "long_horizon_simulation_tournament_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Run governed 3-year and 5-year simulation tournament" if certified else "Expand targeted interval methods without lowering gates",
        "status": "PASS_COLLECTOR_V1_TARGETED_INTERVAL_REMEDIATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_TARGETED_INTERVAL_REMEDIATION_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_targeted_interval_remediation_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
