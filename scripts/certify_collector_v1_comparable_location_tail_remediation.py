from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_comparable_location_tail_remediation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_comparable_location_tail_remediation_summary.json"
    winner_path = OUT_DIR / "collector_v1_comparable_location_tail_winner.csv"
    final_path = OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    winner = pd.read_csv(winner_path)
    final = pd.read_csv(final_path)

    checks = {
        "summary_ready": summary.get("status") == "PASS_COLLECTOR_V1_COMPARABLE_LOCATION_TAIL_REMEDIATION_READY",
        "comparable_route_resolved": summary.get("comparable_route_resolved") is True,
        "zero_unresolved_routes": int(summary.get("final_unresolved_routes", -1)) == 0,
        "four_final_routes": int(summary.get("final_winner_routes", -1)) == 4,
        "winner_promotable": len(winner) == 1 and str(winner.iloc[0].get("promotion_status")) == "PROMOTABLE",
        "winner_coverage_pass": len(winner) == 1 and bool(winner.iloc[0].get("coverage_pass")),
        "winner_tail_pass": len(winner) == 1 and bool(winner.iloc[0].get("tail_balance_pass")),
        "product_holdout_enforced": summary.get("product_holdout_enforced") is True,
        "gates_unchanged": summary.get("original_coverage_and_tail_gates_unchanged") is True,
        "limited_route_delegated": bool(((final["route"].astype(str) == "DIRECT_HISTORY_LIMITED") & (final["promotion_status"].astype(str) == "APPROVED_FAIL_CLOSED_FALLBACK")).any()),
        "all_routes_resolved": bool(final["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"]).all()),
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures
    certification = {
        "block_name": "Collector V1 Comparable Location and Upper-Tail Remediation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(v) for v in checks.values()),
        "critical_failures": failures,
        "comparable_location_tail_remediation_certified": certified,
        "long_horizon_method_stack_certified": certified,
        "scenario_simulation_rebuild_authorized": certified,
        "decision_readiness_tournament_authorized_after_scenario_rebuild": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Rebuild all 40 governed 3-year and 5-year scenario cells from the final four-route method stack",
        "status": "PASS_COLLECTOR_V1_COMPARABLE_LOCATION_TAIL_REMEDIATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_COMPARABLE_LOCATION_TAIL_REMEDIATION_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_comparable_location_tail_remediation_certification.json").write_text(json.dumps(certification, indent=2), encoding="utf-8")
    print(json.dumps(certification, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
