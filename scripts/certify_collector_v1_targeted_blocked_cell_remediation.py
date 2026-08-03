from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_blocked_cell_remediation"


def check(name: str, passed: bool, details: str) -> dict:
    return {"check": name, "passed": bool(passed), "severity": "CRITICAL", "details": details}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_targeted_blocked_cell_remediation_summary.json"
    early_metrics_path = OUT_DIR / "collector_v1_targeted_early_metrics.csv"
    early_winner_path = OUT_DIR / "collector_v1_targeted_early_winner.csv"
    limited_path = OUT_DIR / "collector_v1_limited_365_route_resolution.csv"
    required = [summary_path, early_metrics_path, early_winner_path, limited_path]

    checks: list[dict] = []
    checks.append(check("all targeted remediation artifacts exist", all(p.exists() for p in required), f"missing={[str(p) for p in required if not p.exists()]}"))
    if not all(p.exists() for p in required):
        payload = {
            "block_name": "Collector V1 Targeted Blocked Cell Remediation Certification",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "critical_failures": [c for c in checks if not c["passed"]],
            "targeted_remediation_certified": False,
            "winner_promotion_authorized": False,
            "long_horizon_simulation_authorized": False,
            "production_forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
            "status": "FAIL_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_CERTIFICATION",
        }
        print(json.dumps(payload, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(early_metrics_path)
    winner = pd.read_csv(early_winner_path)
    limited = pd.read_csv(limited_path)

    checks.extend([
        check("targeted remediation builder ready", summary.get("targeted_remediation_ready") is True, f"status={summary.get('status')}"),
        check("early candidate coverage reaches promotion scale", int(summary.get("candidate_products", 0)) >= 30, f"candidate_products={summary.get('candidate_products')}"),
        check("early winner artifact contains one selected candidate", len(winner) == 1, f"rows={len(winner)}"),
        check("early winner meets unchanged promotion gates", len(winner) == 1 and str(winner.iloc[0].get("promotion_status")) == "PROMOTABLE", f"status={winner.iloc[0].get('promotion_status') if len(winner) else 'MISSING'}"),
        check("limited-history 365 uses approved fail-closed delegation", len(limited) == 1 and str(limited.iloc[0].get("resolution_status")) == "APPROVED_FAIL_CLOSED_FALLBACK", f"status={limited.iloc[0].get('resolution_status') if len(limited) else 'MISSING'}"),
        check("both blocked cells resolved", int(summary.get("remaining_blocked_cells", 99)) == 0, f"remaining={summary.get('remaining_blocked_cells')}"),
        check("winner set methodologically complete", summary.get("winner_set_methodologically_complete") is True, f"value={summary.get('winner_set_methodologically_complete')}"),
        check("production remains blocked", summary.get("production_forecasting_authorized") is False and summary.get("purchase_recommendations_authorized") is False and summary.get("uip_delivery_authorized") is False, "production/purchase/UIP remain false"),
    ])

    failures = [c for c in checks if not c["passed"]]
    certified = not failures
    payload = {
        "block_name": "Collector V1 Targeted Blocked Cell Remediation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "critical_failures": failures,
        "targeted_remediation_certified": certified,
        "winner_promotion_authorized": certified,
        "long_horizon_simulation_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Certify complete short-horizon winners and run governed 3-year and 5-year simulations" if certified else "Resolve remaining targeted remediation failures",
        "status": "PASS_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_targeted_blocked_cell_remediation_certification.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame(checks).to_csv(OUT_DIR / "collector_v1_targeted_blocked_cell_remediation_checks.csv", index=False)
    print(json.dumps(payload, indent=2))
    return 0 if certified or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
