from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_purchase_adequacy_tournament_v2"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_final_purchase_adequacy_summary_v2.json"
    results_path = OUT_DIR / "collector_v1_final_purchase_adequacy_results_v2.csv"
    stability_path = OUT_DIR / "collector_v1_final_recommendation_stability_v2.csv"
    compression_path = OUT_DIR / "collector_v1_forecast_compression_diagnostics_v2.json"

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    results = pd.read_csv(results_path) if results_path.exists() else pd.DataFrame()
    stability = pd.read_csv(stability_path) if stability_path.exists() else pd.DataFrame()

    authorized = (
        results.get("purchase_authorization_eligible", pd.Series(dtype=str))
        .astype(str).str.lower().eq("true")
    )
    checks = {
        "summary_exists": summary_path.exists(),
        "results_exist": results_path.exists(),
        "stability_exists": stability_path.exists(),
        "compression_diagnostics_exist": compression_path.exists(),
        "global_model_ready": summary.get("global_model_ready") is True,
        "forecast_compression_pass": bool(summary.get("forecast_compression", {}).get("forecast_compression_pass")),
        "product_count_50": len(results) == 50,
        "product_ids_unique": bool(not results.empty and not results["tcgplayer_product_id"].duplicated().any()),
        "three_price_shocks_per_product": bool(
            not stability.empty
            and len(stability) == 150
            and stability.groupby("tcgplayer_product_id")["price_shock"].nunique().eq(3).all()
        ),
        "individual_product_gates_enforced": summary.get("individual_product_gates_enforced") is True,
        "authorized_products_have_fresh_prices": bool(
            not authorized.any()
            or results.loc[authorized, "price_fresh"].astype(str).str.lower().eq("true").all()
        ),
        "authorized_products_have_listing_depth": bool(
            not authorized.any()
            or results.loc[authorized, "listing_adequate"].astype(str).str.lower().eq("true").all()
        ),
        "authorized_products_are_recommendation_stable": bool(
            not authorized.any()
            or results.loc[authorized, "recommendation_stable"].astype(str).str.lower().eq("true").all()
        ),
        "authorized_products_are_buy_candidates": bool(
            not authorized.any()
            or results.loc[authorized, "recommendation_status"].astype(str).eq("BUY_CANDIDATE").all()
        ),
        "production_still_blocked": summary.get("production_forecasting_authorized") is False,
        "uip_delivery_still_blocked": summary.get("uip_delivery_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures
    authorized_count = int(authorized.sum()) if not results.empty else 0

    certification = {
        "block_name": "Collector V1 Final Purchase Adequacy Tournament V2 Certification",
        "block_version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(v) for v in checks.values()),
        "checks": checks,
        "critical_failures": failures,
        "final_purchase_adequacy_v2_certified": certified,
        "authorized_product_count": authorized_count if certified else 0,
        "individual_product_purchase_recommendations_authorized": bool(certified and authorized_count > 0),
        "maximum_purchase_prices_purchase_authorized_for_eligible_products": bool(certified and authorized_count > 0),
        "blocked_products_remain_unauthorized": True,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Review individually authorized products and refresh blocked product prices or listings as needed",
        "status": "PASS_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_V2_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_V2_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_final_purchase_adequacy_certification_v2.json").write_text(
        json.dumps(certification, indent=2), encoding="utf-8"
    )
    print(json.dumps(certification, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
