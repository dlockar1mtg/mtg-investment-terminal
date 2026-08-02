from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_purchase_adequacy_tournament"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_final_purchase_adequacy_summary.json"
    results_path = OUT_DIR / "collector_v1_final_purchase_adequacy_results.csv"
    stability_path = OUT_DIR / "collector_v1_final_recommendation_stability.csv"
    compression_path = OUT_DIR / "collector_v1_forecast_compression_diagnostics.json"

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    results = pd.read_csv(results_path) if results_path.exists() else pd.DataFrame()
    stability = pd.read_csv(stability_path) if stability_path.exists() else pd.DataFrame()

    checks = {
        "summary_exists": summary_path.exists(),
        "results_exist": results_path.exists(),
        "stability_results_exist": stability_path.exists(),
        "compression_diagnostics_exist": compression_path.exists(),
        "product_count_50": len(results) == 50,
        "product_ids_unique": bool(not results.empty and not results["tcgplayer_product_id"].duplicated().any()),
        "three_price_shocks_per_product": bool(not stability.empty and stability.groupby("tcgplayer_product_id").size().eq(3).all()),
        "analytical_rank_complete": bool(not results.empty and set(pd.to_numeric(results["analytical_rank"], errors="coerce").dropna().astype(int)) == set(range(1, 51))),
        "price_freshness_computed": bool(not results.empty and "price_fresh" in results.columns),
        "listing_adequacy_computed": bool(not results.empty and "listing_adequate" in results.columns),
        "recommendation_stability_computed": bool(not results.empty and "recommendation_stable" in results.columns),
        "transaction_cost_adjusted_prices_positive": bool(not results.empty and (pd.to_numeric(results["net_max_purchase_price_25pct_3y"], errors="coerce") > 0).all()),
        "framework_status_consistent": summary.get("final_purchase_adequacy_ready") is (len(summary.get("critical_failures", [])) == 0),
        "production_still_blocked": summary.get("production_forecasting_authorized") is False,
        "uip_still_blocked": summary.get("uip_delivery_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures

    certification = {
        "block_name": "Collector V1 Final Purchase Adequacy Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(v) for v in checks.values()),
        "checks": checks,
        "critical_failures": failures,
        "final_purchase_adequacy_tournament_certified": certified,
        "analytical_product_rankings_certified": certified,
        "maximum_purchase_price_methodology_certified": certified,
        "live_price_freshness_certified": bool(certified and summary.get("checks", {}).get("all_prices_fresh_within_7_days")),
        "listing_adequacy_certified": bool(certified and summary.get("checks", {}).get("all_products_have_minimum_listing_depth")),
        "forecast_compression_certified": bool(certified and summary.get("checks", {}).get("forecast_compression_pass")),
        "recommendation_stability_certified": bool(certified and summary.get("checks", {}).get("recommendation_stability_computed")),
        "purchase_recommendations_authorized": bool(certified and summary.get("purchase_recommendations_authorized")),
        "authorized_product_count": int(summary.get("authorized_product_count", 0)) if certified else 0,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Review authorized products and publish a governed purchase-screen output, or remediate any failed freshness, liquidity, compression, or stability gate",
        "status": "PASS_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_final_purchase_adequacy_certification.json").write_text(json.dumps(certification, indent=2), encoding="utf-8")
    print(json.dumps(certification, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
