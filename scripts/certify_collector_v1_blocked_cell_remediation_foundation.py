from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_blocked_cell_remediation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    required = {
        "summary": OUT_DIR / "collector_v1_blocked_cell_remediation_summary.json",
        "coverage": OUT_DIR / "collector_v1_early_coverage_reconciliation.csv",
        "blocked": OUT_DIR / "collector_v1_blocked_winner_cells.csv",
        "plan": OUT_DIR / "collector_v1_blocked_cell_candidate_plan.csv",
        "gaps": OUT_DIR / "collector_v1_blocked_cell_gap_register.csv",
    }
    failures: list[dict] = []

    missing = [str(p.relative_to(ROOT)) for p in required.values() if not p.exists()]
    failures.append({"check": "all remediation artifacts exist", "passed": not missing, "details": f"missing={missing}"})

    if not missing:
        summary = json.loads(required["summary"].read_text(encoding="utf-8"))
        coverage = pd.read_csv(required["coverage"])
        blocked = pd.read_csv(required["blocked"])
        plan = pd.read_csv(required["plan"])
        gaps = pd.read_csv(required["gaps"])

        checks = [
            ("foundation summary ready", bool(summary.get("remediation_foundation_ready")), f"status={summary.get('status')}"),
            ("exactly two blocked winner cells", len(blocked) == 2, f"rows={len(blocked)}"),
            ("at least 30 realized first-year products", int(summary.get("realized_first_year_products", 0)) >= 30, f"count={summary.get('realized_first_year_products')}"),
            ("coverage reconciliation includes all realized products", len(coverage) == int(summary.get("realized_first_year_products", -1)), f"rows={len(coverage)}"),
            ("candidate plan covers both blocked cells", plan["blocked_cell"].nunique() == 2, f"cells={sorted(plan['blocked_cell'].unique().tolist())}"),
            ("authorized remediation candidates exist", int((plan["status"] == "AUTHORIZED_TO_BUILD").sum()) >= 4, f"authorized={int((plan['status'] == 'AUTHORIZED_TO_BUILD').sum())}"),
            ("pair score remains explicitly unregistered", bool((gaps["gap"] == "comparable_similarity_score").any()), "gap recorded"),
            ("winner promotion remains blocked", summary.get("winner_promotion_authorized") is False, f"value={summary.get('winner_promotion_authorized')}"),
            ("long horizon remains blocked", summary.get("long_horizon_simulation_authorized") is False, f"value={summary.get('long_horizon_simulation_authorized')}"),
        ]
        for name, passed, details in checks:
            failures.append({"check": name, "passed": bool(passed), "details": details})

    critical = [row for row in failures if not row["passed"]]
    result = {
        "block_name": "Collector V1 Blocked Cell Remediation Foundation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(failures),
        "passed_checks": len(failures) - len(critical),
        "critical_failures": critical,
        "blocked_cell_remediation_foundation_certified": not critical,
        "targeted_candidate_build_authorized": not critical,
        "winner_promotion_authorized": False,
        "long_horizon_simulation_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build targeted limited-history 365-day and early-opportunity remediation candidates",
        "status": "PASS_COLLECTOR_V1_BLOCKED_CELL_REMEDIATION_FOUNDATION_CERTIFIED" if not critical else "FAIL_COLLECTOR_V1_BLOCKED_CELL_REMEDIATION_FOUNDATION_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_blocked_cell_remediation_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pd.DataFrame(failures).to_csv(OUT_DIR / "collector_v1_blocked_cell_remediation_checks.csv", index=False)
    print(json.dumps(result, indent=2))
    return 1 if args.strict and critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
