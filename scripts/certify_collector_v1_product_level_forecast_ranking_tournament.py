from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_product_level_forecast_ranking_tournament"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_product_level_forecast_ranking_tournament_summary.json"
    rankings_path = OUT_DIR / "collector_v1_product_level_rankings.csv"
    shocks_path = OUT_DIR / "collector_v1_product_price_shock_tournament.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    rankings = pd.read_csv(rankings_path) if rankings_path.exists() else pd.DataFrame()
    shocks = pd.read_csv(shocks_path) if shocks_path.exists() else pd.DataFrame()

    checks = {
        "summary_exists": summary_path.exists(),
        "rankings_exist": rankings_path.exists(),
        "shock_tournament_exists": shocks_path.exists(),
        "product_count_50": len(rankings) == 50,
        "product_ids_unique": bool(not rankings.empty and not rankings["tcgplayer_product_id"].duplicated().any()),
        "three_price_shocks_per_product": bool(len(shocks) == 150 and shocks.groupby("tcgplayer_product_id").size().eq(3).all()),
        "analytical_rank_complete": bool(not rankings.empty and set(rankings["analytical_rank"].astype(int)) == set(range(1, 51))),
        "ranking_stability_computed": bool(not rankings.empty and rankings["ranking_stable"].notna().all()),
        "maximum_price_metrics_positive": bool(not rankings.empty and (pd.to_numeric(rankings["max_purchase_price_25pct_3y"], errors="coerce") > 0).all() and (pd.to_numeric(rankings["max_purchase_price_25pct_5y"], errors="coerce") > 0).all()),
        "tournament_ready": summary.get("product_level_tournament_ready") is True,
        "live_price_freshness_still_blocked": summary.get("live_price_freshness_certified") is False,
        "recommendations_still_blocked": summary.get("purchase_recommendations_authorized") is False,
        "production_still_blocked": summary.get("production_forecasting_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures

    certification = {
        "block_name": "Collector V1 Product-Level Forecast and Ranking Tournament Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(v) for v in checks.values()),
        "checks": checks,
        "critical_failures": failures,
        "product_level_forecast_ranking_tournament_certified": certified,
        "analytical_product_rankings_certified": certified,
        "maximum_purchase_price_methodology_certified": certified,
        "maximum_purchase_prices_purchase_authorized": False,
        "live_price_freshness_certification_required": True,
        "final_recommendation_stability_certification_required": True,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Certify live current-price freshness and final recommendation stability before purchase authorization",
        "status": "PASS_COLLECTOR_V1_PRODUCT_LEVEL_FORECAST_RANKING_TOURNAMENT_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_PRODUCT_LEVEL_FORECAST_RANKING_TOURNAMENT_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_product_level_forecast_ranking_tournament_certification.json").write_text(json.dumps(certification, indent=2), encoding="utf-8")
    print(json.dumps(certification, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
