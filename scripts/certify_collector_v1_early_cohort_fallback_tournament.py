from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_cohort_fallback_tournament"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_early_cohort_fallback_summary.json"
    metrics_path = OUT_DIR / "collector_v1_early_cohort_fallback_metrics.csv"
    winner_path = OUT_DIR / "collector_v1_early_cohort_fallback_winner.csv"
    failures: list[dict] = []

    if not summary_path.exists() or not metrics_path.exists() or not winner_path.exists():
        failures.append({"check": "required outputs exist", "severity": "CRITICAL"})
        summary = {}
        metrics = pd.DataFrame()
        winner = pd.DataFrame()
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        metrics = pd.read_csv(metrics_path)
        winner = pd.read_csv(winner_path)

    checks = [
        ("coverage reaches at least 30 products", int(summary.get("eligible_products", 0)) >= 30), f"eligible_products={summary.get('eligible_products')}") ,
        ("peer features are not required", summary.get("peer_features_required") is False, f"value={summary.get('peer_features_required')}") ,
        ("leave-one-product-out enforced", summary.get("leave_one_product_out_enforced") is True, f"value={summary.get('leave_one_product_out_enforced')}") ,
        ("feature cutoff enforced", summary.get("feature_cutoff_enforced") is True, f"value={summary.get('feature_cutoff_enforced')}") ,
        ("candidate metrics exist", not metrics.empty, f"rows={len(metrics)}") ,
        ("winner exists", len(winner) == 1, f"rows={len(winner)}") ,
        ("winner meets unchanged gates", bool(not winner.empty and str(winner.iloc[0].get("promotion_status")) == "PROMOTABLE"), f"status={winner.iloc[0].get('promotion_status') if not winner.empty else None}") ,
        ("fallback resolved", summary.get("early_cohort_fallback_resolved") is True, f"value={summary.get('early_cohort_fallback_resolved')}") ,
        ("production remains blocked", summary.get("production_forecasting_authorized") is False, f"value={summary.get('production_forecasting_authorized')}") ,
        ("purchase recommendations remain blocked", summary.get("purchase_recommendations_authorized") is False, f"value={summary.get('purchase_recommendations_authorized')}") ,
    ]
    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "passed": False, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Early Cohort Fallback Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": len(checks) - len(failures),
        "critical_failures": failures,
        "early_cohort_fallback_certified": certified,
        "winner_promotion_authorized": certified,
        "long_horizon_simulation_authorized_after_final_winner_certification": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Certify final short-horizon winner set, then run governed 3-year and 5-year simulations" if certified else "Improve cohort fallback candidates without lowering gates",
        "status": "PASS_COLLECTOR_V1_EARLY_COHORT_FALLBACK_TOURNAMENT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_EARLY_COHORT_FALLBACK_TOURNAMENT_CERTIFICATION",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "collector_v1_early_cohort_fallback_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
