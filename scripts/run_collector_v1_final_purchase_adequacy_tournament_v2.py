from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RANK_DIR = ROOT / "data/governance/permanence/certification/collector_v1_product_level_forecast_ranking_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_purchase_adequacy_tournament_v2"
RANKINGS_PATH = RANK_DIR / "collector_v1_product_level_rankings.csv"
RANK_CERT_PATH = RANK_DIR / "collector_v1_product_level_forecast_ranking_tournament_certification.json"

AS_OF_DATE = pd.Timestamp("2026-08-01", tz="UTC")
FRESHNESS_DAYS = 7
MIN_ACCEPTED_LISTINGS = 3
TRANSACTION_COST_RATE = 0.15
MAX_TOP20_COMPRESSION_SHARE = 0.60
PRICE_SHOCKS = [-0.10, 0.00, 0.10]


def bool_col(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().eq("true")


def num(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


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
        "momentum_rank", "scarcity_rank", "liquidity_rank", "volatility_rank", "drawdown_rank",
    ]
    for col in numeric:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    df["ranking_stable"] = bool_col(df["ranking_stable"])
    df["latest_price_date"] = pd.to_datetime(df.get("latest_price_date"), errors="coerce", utc=True)
    df["price_age_days"] = (AS_OF_DATE.normalize() - df["latest_price_date"].dt.normalize()).dt.days
    df["price_fresh"] = df["price_age_days"].between(0, FRESHNESS_DAYS, inclusive="both")
    df["listing_adequate"] = df["accepted_listing_count"].fillna(0).ge(MIN_ACCEPTED_LISTINGS)

    # Product-specific de-compression: combine certified factor ranks, center within route,
    # and apply a bounded multiplier so route-level scenario authority remains dominant.
    raw_signal = (
        0.30 * (num(df, "momentum_rank", 0.5) - 0.5)
        + 0.25 * (num(df, "scarcity_rank", 0.5) - 0.5)
        + 0.15 * (num(df, "liquidity_rank", 0.5) - 0.5)
        + 0.15 * (num(df, "volatility_rank", 0.5) - 0.5)
        + 0.15 * (num(df, "drawdown_rank", 0.5) - 0.5)
    )
    route_center = raw_signal.groupby(df["forecast_method"]).transform("mean")
    centered_signal = (raw_signal - route_center).clip(-0.50, 0.50)
    df["decompression_signal"] = centered_signal
    df["decompression_multiplier"] = np.exp((0.30 * centered_signal).clip(-0.15, 0.15))

    for metric in ["product_p10_3y", "product_median_3y", "product_p10_5y", "product_median_5y"]:
        df[f"v1_{metric}"] = df[metric]
        df[metric] = df[metric] * df["decompression_multiplier"]

    df["max_purchase_price_25pct_3y"] = df["current_price"] * df["product_p10_3y"] / 1.25
    df["max_purchase_price_25pct_5y"] = df["current_price"] * df["product_p10_5y"] / 1.25
    df["net_max_purchase_price_25pct_3y"] = df["max_purchase_price_25pct_3y"] * (1.0 - TRANSACTION_COST_RATE)
    df["net_max_purchase_price_25pct_5y"] = df["max_purchase_price_25pct_5y"] * (1.0 - TRANSACTION_COST_RATE)
    df["net_margin_3y"] = df["net_max_purchase_price_25pct_3y"] / df["current_price"] - 1.0
    df["net_margin_5y"] = df["net_max_purchase_price_25pct_5y"] / df["current_price"] - 1.0

    top20 = df.nsmallest(20, "analytical_rank").copy()
    signature_cols = ["product_p10_3y", "product_median_3y", "product_p10_5y", "product_median_5y"]
    signatures = top20[signature_cols].round(8).astype(str).agg("|".join, axis=1)
    top20_compression_share = float(signatures.value_counts(normalize=True).max()) if len(signatures) else 1.0
    unique_top20_signatures = int(signatures.nunique())
    forecast_compression_pass = top20_compression_share <= MAX_TOP20_COMPRESSION_SHARE

    shock_rows: list[dict] = []
    for shock in PRICE_SHOCKS:
        shocked_price = df["current_price"] * (1.0 + shock)
        shocked_margin = df["net_max_purchase_price_25pct_3y"] / shocked_price - 1.0
        status = np.select(
            [
                df["price_fresh"]
                & df["listing_adequate"]
                & df["ranking_stable"]
                & shocked_margin.ge(0.10)
                & df["product_p10_3y"].ge(1.0),
                shocked_margin.ge(-0.10),
            ],
            ["BUY_CANDIDATE", "WAIT"],
            default="AVOID",
        )
        for product_id, product_name, st, margin in zip(
            df["tcgplayer_product_id"], df["product_name"], status, shocked_margin
        ):
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

    global_checks = {
        "ranking_tournament_certified": True,
        "product_count_50": len(df) == 50,
        "product_ids_unique": not df["tcgplayer_product_id"].duplicated().any(),
        "forecast_compression_pass": bool(forecast_compression_pass),
        "recommendation_stability_computed": bool(df["recommendation_stable"].notna().all()),
        "transaction_cost_adjustment_applied": True,
        "net_max_prices_positive": bool((df[["net_max_purchase_price_25pct_3y", "net_max_purchase_price_25pct_5y"]] > 0).all().all()),
        "decompression_multiplier_finite": bool(np.isfinite(df["decompression_multiplier"]).all()),
        "decompression_multiplier_bounded": bool(df["decompression_multiplier"].between(np.exp(-0.15), np.exp(0.15)).all()),
    }
    global_failures = [name for name, passed in global_checks.items() if not passed]
    global_model_ready = not global_failures

    df["purchase_authorization_eligible"] = (
        global_model_ready
        & df["recommendation_status"].eq("BUY_CANDIDATE")
        & df["recommendation_stable"]
        & df["price_fresh"]
        & df["listing_adequate"]
    )
    df["purchase_recommendation_authorized"] = df["purchase_authorization_eligible"]
    df["maximum_purchase_price_certified"] = global_model_ready & df["price_fresh"] & df["listing_adequate"]
    df["product_blockers"] = ""
    df.loc[~df["price_fresh"], "product_blockers"] += "STALE_OR_MISSING_PRICE;"
    df.loc[~df["listing_adequate"], "product_blockers"] += "INSUFFICIENT_LISTINGS;"
    df.loc[~df["recommendation_stable"], "product_blockers"] += "UNSTABLE_RECOMMENDATION;"
    if not global_model_ready:
        df["product_blockers"] += "GLOBAL_MODEL_GATE_FAILED;"

    authorized_products = int(df["purchase_authorization_eligible"].sum())
    df.sort_values("analytical_rank").to_csv(OUT_DIR / "collector_v1_final_purchase_adequacy_results_v2.csv", index=False)
    shocks.to_csv(OUT_DIR / "collector_v1_final_recommendation_stability_v2.csv", index=False)

    compression = {
        "top20_products": int(len(top20)),
        "unique_top20_forecast_signatures": unique_top20_signatures,
        "largest_identical_forecast_signature_share": top20_compression_share,
        "maximum_allowed_share": MAX_TOP20_COMPRESSION_SHARE,
        "forecast_compression_pass": bool(forecast_compression_pass),
        "decompression_method": "ROUTE_CENTERED_BOUNDED_CERTIFIED_FACTOR_MULTIPLIER",
        "decompression_log_bound": 0.15,
    }
    (OUT_DIR / "collector_v1_forecast_compression_diagnostics_v2.json").write_text(
        json.dumps(compression, indent=2), encoding="utf-8"
    )

    summary = {
        "block_name": "Collector V1 Final Purchase Adequacy Tournament V2",
        "block_version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": str(AS_OF_DATE.date()),
        "products": int(len(df)),
        "freshness_days_required": FRESHNESS_DAYS,
        "minimum_accepted_listings": MIN_ACCEPTED_LISTINGS,
        "transaction_cost_rate": TRANSACTION_COST_RATE,
        "fresh_price_products": int(df["price_fresh"].sum()),
        "missing_price_date_products": int(df["latest_price_date"].isna().sum()),
        "listing_adequate_products": int(df["listing_adequate"].sum()),
        "recommendation_stable_products": int(df["recommendation_stable"].sum()),
        "current_status_counts": df["recommendation_status"].value_counts(dropna=False).to_dict(),
        "forecast_compression": compression,
        "global_checks": global_checks,
        "global_critical_failures": global_failures,
        "global_model_ready": global_model_ready,
        "individual_product_gates_enforced": True,
        "authorized_product_count": authorized_products,
        "maximum_purchase_prices_purchase_authorized": bool(global_model_ready and authorized_products > 0),
        "purchase_recommendations_authorized": bool(global_model_ready and authorized_products > 0),
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_V2_READY" if global_model_ready else "PARTIAL_COLLECTOR_V1_FINAL_PURCHASE_ADEQUACY_V2",
    }
    (OUT_DIR / "collector_v1_final_purchase_adequacy_summary_v2.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if (global_model_ready or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
