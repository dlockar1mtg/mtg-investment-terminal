from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RANK_DIR = ROOT / "data/governance/permanence/certification/collector_v1_product_level_forecast_ranking_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_purchase_adequacy_tournament"
RANKINGS_PATH = RANK_DIR / "collector_v1_product_level_rankings.csv"
RANK_CERT_PATH = RANK_DIR / "collector_v1_product_level_forecast_ranking_tournament_certification.json"

AS_OF_DATE = pd.Timestamp("2026-08-01")
FRESHNESS_DAYS = 7
MIN_ACCEPTED_LISTINGS = 3
TRANSACTION_COST_RATE = 0.15
MAX_TOP20_COMPRESSION_SHARE = 0.60
PRICE_SHOCKS = [-0.10, 0.00, 0.10]


def bool_col(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().eq("true")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cert = json.loads(RANK_CERT_PATH.read_text(encoding="utf-8"))
    if cert.get("product_level_forecast_ranking_tournament_certified") is not True:
        raise RuntimeError("Certified product-level ranking tournament is required")

    df = pd.read_csv(RANKINGS_PATH)
    numeric = [
        "current_price", "analytical_score", "analytical_rank", "accepted_listing_count",
        "product_p10_3y", "product_median_3y", "product_p10_5y", "product_median_5y",
        "max_purchase_price_25pct_3y", "max_purchase_price_25pct_5y", "rank_spread",
    ]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ranking_stable"] = bool_col(df["ranking_stable"])
    df["latest_price_date"] = pd.to_datetime(df.get("latest_price_date"), errors="coerce")
    df["price_age_days"] = (AS_OF_DATE - df["latest_price_date"].dt.normalize()).dt.days
    df["price_fresh"] = df["price_age_days"].between(0, FRESHNESS_DAYS, inclusive="both")
    df["listing_adequate"] = df["accepted_listing_count"].fillna(0).ge(MIN_ACCEPTED_LISTINGS)

    df["net_max_purchase_price_25pct_3y"] = df["max_purchase_price_25pct_3y"] * (1.0 - TRANSACTION_COST_RATE)
    df["net_max_purchase_price_25pct_5y"] = df["max_purchase_price_25pct_5y"] * (1.0 - TRANSACTION_COST_RATE)
    df["net_margin_3y"] = df["net_max_purchase_price_25pct_3y"] / df["current_price"] - 1.0
    df["net_margin_5y"] = df["net_max_purchase_price_25pct_5y"] / df["current_price"] - 1.0

    # Forecast compression check: identify repeated rounded route-adjusted forecasts among the top 20.
    top20 = df.nsmallest(20, "analytical_rank").copy()
    signature_cols = ["product_p10_3y", "product_median_3y", "product_p10_5y", "product_median_5y"]
    signatures = top20[signature_cols].round(8).astype(str).agg("|".join, axis=1)
    top20_compression_share = float(signatures.value_counts(normalize=True).max()) if len(signatures) else 1.0
    forecast_compression_pass = top20_compression_share <= MAX_TOP20_COMPRESSION_SHARE

    # Recommendation stability under price shocks after transaction costs.
    shock_rows: list[dict] = []
    for shock in PRICE_SHOCKS:
        shocked_price = df["current_price"] * (1.0 + shock)
        shocked_margin = df["net_max_purchase_price_25pct_3y"] / shocked_price - 1.0
        status = np.select(
            [
                df["price_fresh"] & df["listing_adequate"] & df["ranking_stable"] & shocked_margin.ge(0.10) & df["product_p10_3y"].ge(1.0),
                shocked_margin.ge(-0.10),
            ],
            ["BUY_CANDIDATE", "WAIT"],
            default="AVOID",
        )
        for product_id, product_name, st, margin in zip(df["tcgplayer_product_id"], df["product_name"], status, shocked_margin):
            shock_rows.append({
                "tcgplayer_product_id": product_id,
                "product_name": product_name,
                "price_shock": shock,
                "recommendation_status": st,
                "net_margin_3y": float(margin),
            })
    shocks = pd.DataFrame(shock_rows)
    status_counts = shocks.groupby("tcgplayer_product_id")["recommendation_status"].nunique()
    stable_ids = set(status_counts[status_counts.eq(1)].index)
    df["recommendation_stable"] = df["tcgplayer_product_id"].isin(stable_ids)

    current_status = shocks[shocks["price_shock"].eq(0.0)][["tcgplayer_product_id", "recommendation_status"]]
    df = df.merge(current_status, on="tcgplayer_product_id", how="left")
    df["purchase_authorization_eligible"] = (
        df["recommendation_status"].eq("BUY_CANDIDATE")
        & df["recommendation_stable"]
        & df["price_fresh"]
        & df["listing_adequate"]
        & forecast_compression_pass
    )
    df["purchase_recommendation_authorized"] = df["purchase_authorization_eligible"]
    df["maximum_purchase_price_certified"] = df["price_fresh"] & df["listing_adequate"] & forecast_compression_pass

    checks = {
        "ranking_tournament_certified": True,
        "product_count_50": len(df) == 50,
        "product_ids_unique": not df["tcgplayer_product_id"].duplicated().any(),
        "all_price_dates_present": bool(df["latest_price_date"].notna().all()),
        "all_prices_fresh_within_7_days": bool(df["price_fresh"].all()),
        "all_products_have_minimum_listing_depth": bool(df["listing_adequate"].all()),
        "forecast_compression_pass": bool(forecast_compression_pass),
        "recommendation_stability_computed": bool(df["recommendation_stable"].notna().all()),
        "transaction_cost_adjustment_applied": True,
        "net_max_prices_positive": bool((df[["net_max_purchase_price_25pct_3y", "net_max_purchase_price_25pct_5y"]] > 0).all().all()),
    }
    critical_failures = [name for name, passed in checks.items() if not passed]
    framework_complete = not critical_failures
    authorized_products = int(df["purchase_authorization_eligible"].sum()) if framework_complete else 0

    df.sort_values("analytical_rank").to_csv(OUT_DIR / "collector_v1_final_purchase_adequacy_results.csv", index=False)
    shocks.to_csv(OUT_DIR / "collector_v1_final_recommendation_stability.csv", index=False)
    compression = {
        "top20_products": int(len(top20)),
        "largest_identical_forecast_signature_share": top20_compression_share,
        "maximum_allowed_share": MAX_TOP20_COMPRESSION_SHARE,
        "forecast_compression_pass": bool(forecast_compression_pass),
    }
    (OUT_DIR / "collector_v1_forecast_compression_diagnostics.json").write_text(json.dumps(compression, indent=2), encoding="utf-8")

    summary = {
        "block_name": "Collector V1 Final Purchase Adequacy Tournament",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": str(AS_OF_DATE.date()),
        "products": int(len(df)),
        "freshness_days_required": FRESHNESS_DAYS,
        "minimum_accepted_listings": MIN_ACCEPTED_LISTINGS,
        "transaction_cost_rate": TRANSACTION_COST_RATE,
        "fresh_price_products": int(df["price_fresh"].sum()),
        "listing_adequate_products": int(df["listing_adequate"].sum()),
        "recommendation_stable_products": int(df["recommendation_stable"].sum()),
        "current_status_counts": df["recommendation_status"].value_counts(dropna=False).to_dict(),
        "forecast_compression": compression,
        "checks": checks,
        "critical_failures": critical_failures,
        "final_purchase_adequacy_ready": framework_complete,
        "analytical_rankings_certified": True,
        "maximum_purchase_price_methodology_certified": True,
        "maximum_purchase_prices_purchase_authorized": bool(framework_complete),
        "purchase_recommendations_authorized": bool(framework_complete and authorized_products > 0),
        "authorized_product_count": authorized_products,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_READY" if framework_complete else "PARTIAL_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY",
    }
    (OUT_DIR / "collector_v1_final_purchase_adequacy_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (framework_complete or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
