from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_comparable_cluster_envelope_remediation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_comparable_cluster_envelope_remediation_summary.json"
    winner_path = OUT_DIR / "collector_v1_comparable_cluster_envelope_winner.csv"
    final_path = OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv"

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    winner = pd.read_csv(winner_path) if winner_path.exists() else pd.DataFrame()
    final = pd.read_csv(final_path) if final_path.exists() else pd.DataFrame()

    checks = {
        "summary_exists": summary_path.exists(),
        "winner_exists": winner_path.exists() and len(winner) == 1,
        "final_manifest_exists": final_path.exists(),
        "comparable_route_resolved": summary.get("comparable_route_resolved") is True,
        "four_final_routes": len(final) == 4,
        "zero_unresolved_routes": summary.get("final_unresolved_routes") == 0,
        "product_holdout_enforced": summary.get("product_holdout_enforced") is True,
        "original_gates_unchanged": summary.get("original_coverage_and_tail_gates_unchanged") is True,
        "scenario_rebuild_authorized": summary.get("scenario_simulation_rebuild_authorized") is True,
        "production_false": summary.get("production_forecasting_authorized") is False,
        "purchase_false": summary.get("purchase_recommendations_authorized") is False,
        "uip_false": summary.get("uip_delivery_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures
    payload = {
        "block_name": "Collector V1 Comparable Cluster Envelope Remediation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "comparable_cluster_envelope_remediation_certified": certified,
        "long_horizon_method_stack_certified": certified,
        "scenario_simulation_rebuild_authorized": certified,
        "decision_readiness_tournament_authorized_after_scenario_rebuild": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Rebuild final four-route 3-year and 5-year scenario simulation authority",
        "status": "PASS_COLLECTOR_V1_COMPARABLE_CLUSTER_ENVELOPE_REMEDIATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_COMPARABLE_CLUSTER_ENVELOPE_REMEDIATION_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_comparable_cluster_envelope_remediation_certification.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
