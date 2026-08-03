from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_decision_readiness_tournament"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_decision_readiness_tournament_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required_outputs = [
        "collector_v1_decision_readiness_route_scenario_metrics.csv",
        "collector_v1_decision_readiness_scenario_monotonicity.csv",
        "collector_v1_decision_readiness_rank_stability.csv",
        "collector_v1_decision_readiness_purchase_price_stability.csv",
    ]
    checks = {
        "summary_exists": summary_path.exists(),
        "all_required_outputs_exist": all((OUT_DIR / name).exists() for name in required_outputs),
        "scenario_cells_equal_40": summary.get("scenario_cells") == 40,
        "no_critical_failures": summary.get("critical_failures") == [],
        "decision_framework_ready": summary.get("decision_framework_ready") is True,
        "current_product_application_authorized": summary.get("current_product_application_authorized_after_certification") is True,
        "product_ranking_not_prematurely_certified": summary.get("product_ranking_certified") is False,
        "purchase_prices_not_prematurely_certified": summary.get("maximum_purchase_prices_certified") is False,
        "production_forecasting_not_authorized": summary.get("production_forecasting_authorized") is False,
        "purchase_recommendations_not_authorized": summary.get("purchase_recommendations_authorized") is False,
        "uip_delivery_not_authorized": summary.get("uip_delivery_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures
    certification = {
        "block_name": "Collector V1 Decision-Readiness Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(v) for v in checks.values()),
        "critical_failures": failures,
        "decision_readiness_tournament_certified": certified,
        "current_product_application_authorized": certified,
        "product_level_ranking_tournament_required": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Apply certified route stack to current governed products and run product-level ranking and maximum-purchase-price certification",
        "status": "PASS_COLLECTOR_V1_DECISION_READINESS_TOURNAMENT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_DECISION_READINESS_TOURNAMENT_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_decision_readiness_tournament_certification.json").write_text(json.dumps(certification, indent=2), encoding="utf-8")
    print(json.dumps(certification, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
