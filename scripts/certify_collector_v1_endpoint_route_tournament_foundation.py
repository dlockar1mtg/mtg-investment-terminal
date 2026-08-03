from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_v1_endpoint_route_tournament_foundation"
SUMMARY = BASE / "collector_v1_endpoint_route_tournament_foundation_summary.json"
CELLS = BASE / "collector_v1_tournament_cells.csv"
PROMOTION = BASE / "collector_v1_promotion_matrix.csv"
GAPS = BASE / "collector_v1_tournament_gap_register.csv"
OUT = BASE / "collector_v1_endpoint_route_tournament_foundation_certification.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    checks = []
    required = [SUMMARY, CELLS, PROMOTION, GAPS]
    missing = [str(p) for p in required if not p.exists()]
    checks.append({"check": "all tournament foundation artifacts exist", "passed": not missing, "details": f"missing={missing}"})

    if missing:
        result = {
            "block_name": "Collector V1 Endpoint-Route Tournament Foundation Certification",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "critical_failures": [c for c in checks if not c["passed"]],
            "endpoint_route_tournament_foundation_certified": False,
            "expanded_tournament_authorized": False,
            "production_forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
            "status": "FAIL_COLLECTOR_V1_ENDPOINT_ROUTE_TOURNAMENT_FOUNDATION_CERTIFICATION",
        }
        OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    cells = pd.read_csv(CELLS, low_memory=False)
    promotion = pd.read_csv(PROMOTION, low_memory=False)
    gaps = pd.read_csv(GAPS, low_memory=False)

    checks.extend([
        {"check": "foundation reports readiness", "passed": bool(summary.get("tournament_foundation_ready")), "details": f"status={summary.get('status')}"},
        {"check": "all nine primary route-horizon cells exist", "passed": int(summary.get("observed_price_cells", 0)) == 9 and not summary.get("missing_price_cells"), "details": f"observed={summary.get('observed_price_cells')} missing={summary.get('missing_price_cells')}"},
        {"check": "early-opportunity candidates included", "passed": bool((cells.get("tournament_lane", pd.Series(dtype=str)) == "EARLY_OPPORTUNITY_COMPARABLE_TRANSFER").any()), "details": "dedicated short-history lane required"},
        {"check": "ranking and price objectives remain separate", "passed": {"PRICE_FORECAST", "EARLY_WINNER_RANKING"}.issubset(set(cells.get("selection_objective", []))), "details": "prevents one metric from selecting all winners"},
        {"check": "promotion matrix is nonempty", "passed": len(promotion) > 0, "details": f"rows={len(promotion)}"},
        {"check": "gap register includes expanded tournament", "passed": "expanded_model_families" in set(gaps.get("gap", [])), "details": "full tournament remains required"},
        {"check": "gap register includes comparable similarity", "passed": "comparable_similarity_score" in set(gaps.get("gap", [])), "details": "high-priority V1 input connection"},
        {"check": "gap register includes interval calibration", "passed": "prediction_interval_calibration" in set(gaps.get("gap", [])), "details": "required before production"},
        {"check": "long-horizon simulation remains gated", "passed": not bool(summary.get("long_horizon_simulation_authorized_now")), "details": "must wait for calibrated short-horizon winners"},
        {"check": "production and purchases remain blocked", "passed": not any([summary.get("production_forecasting_authorized"), summary.get("purchase_recommendations_authorized"), summary.get("uip_delivery_authorized")]), "details": "no premature authorization"},
    ])

    failures = [c for c in checks if not c["passed"]]
    certified = not failures
    result = {
        "block_name": "Collector V1 Endpoint-Route Tournament Foundation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "endpoint_route_tournament_foundation_certified": certified,
        "expanded_tournament_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Run expanded endpoint-route tournament with product/cohort holdouts, similarity-weighted comparables, bias correction, and interval calibration",
        "status": "PASS_COLLECTOR_V1_ENDPOINT_ROUTE_TOURNAMENT_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_ENDPOINT_ROUTE_TOURNAMENT_FOUNDATION_CERTIFICATION",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
