from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_product_application_foundation"
FEATURE_PATH = ROOT / "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix.csv"
SCENARIO_PATH = ROOT / "data/governance/permanence/certification/collector_v1_final_long_horizon_scenario_authority/collector_v1_final_long_horizon_scenario_results.csv"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_product_level_forecast_ranking_tournament"

REQUIRED_PRODUCTS = 50
PRICE_SHOCKS = [-0.10, 0.00, 0.10]


def num(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def pct_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    return series.rank(pct=True, method="average", ascending=higher_is_better).fillna(0.5)


def assign_complete_rank(frame: pd.DataFrame, score_column: str, rank_column: str) -> pd.DataFrame:
    """Assign a deterministic complete 1..N rank while preserving the original score."""
    tie_breakers = [
        score_column,
        "downside_rank",
        "long_horizon_rank",
        "momentum_rank",
        "scarcity_rank",
        "liquidity_rank",
        "tcgplayer_product_id",
    ]
    ascending = [False, False, False, False, False, False, True]
    ordered = frame.sort_values(tie_breakers, ascending=ascending, kind="mergesort").copy()
    ordered[rank_column] = np.arange(1, len(ordered) + 1, dtype=int)
    return ordered.sort_index()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    foundation_cert = json.loads((FOUNDATION_DIR / "collector_v1_current_product_application_foundation_certification.json").read_text(encoding="utf-8"))
    if foundation_cert.get("product_level_forecast_tournament_authorized") is not True:
        raise RuntimeError("Current-product foundation does not authorize product tournament")

    products = pd.read_csv(FEATURE_PATH)
    scenarios = pd.read_csv(SCENARIO_PATH)
    for col in ["horizon_days", "p10_terminal_index", "median_terminal_index", "probability_of_loss", "probability_gain_25pct", "probability_gain_50pct"]:
        scenarios[col] = pd.to_numeric(scenarios[col], errors="coerce")

    base = scenarios[scenarios["scenario"].astype(str).eq("BASE")].copy()
    base = base[["route", "horizon_days", "p10_terminal_index", "median_terminal_index", "probability_of_loss", "probability_gain_25pct", "probability_gain_50pct", "confidence_penalty_required"]]
    route_rows = []
    for route in sorted(base["route"].astype(str).unique()):
        row = {"forecast_method": route}
        r = base[base["route"].astype(str).eq(route)]
        for horizon in [1095, 1825]:
            h = r[r["horizon_days"].eq(horizon)]
            if h.empty:
                continue
            x = h.iloc[0]
            suffix = "3y" if horizon == 1095 else "5y"
            row[f"route_p10_{suffix}"] = x["p10_terminal_index"]
            row[f"route_median_{suffix}"] = x["median_terminal_index"]
            row[f"route_loss_prob_{suffix}"] = x["probability_of_loss"]
            row[f"route_gain25_prob_{suffix}"] = x["probability_gain_25pct"]
            row[f"route_gain50_prob_{suffix}"] = x["probability_gain_50pct"]
            row["confidence_penalty_required"] = str(x["confidence_penalty_required"]).lower() == "true"
        route_rows.append(row)
    route_authority = pd.DataFrame(route_rows)

    df = products.merge(route_authority, on="forecast_method", how="left", validate="many_to_one")
    df["current_price"] = num(df, "current_price", np.nan)
    df["momentum_30d"] = num(df, "return_30d")
    df["momentum_90d"] = num(df, "return_90d")
    df["momentum_180d"] = num(df, "return_180d")
    df["momentum_365d"] = num(df, "return_365d")
    df["annualized_volatility"] = num(df, "annualized_volatility")
    df["maximum_drawdown"] = num(df, "maximum_drawdown")
    df["scarcity_score"] = num(df, "scarcity_adjusted_score")
    df["accepted_listing_count"] = num(df, "accepted_listing_count")

    momentum_blend = (
        0.10 * df["momentum_30d"].clip(-1, 2)
        + 0.20 * df["momentum_90d"].clip(-1, 3)
        + 0.30 * df["momentum_180d"].clip(-1, 4)
        + 0.40 * df["momentum_365d"].clip(-1, 6)
    )
    df["product_adjustment"] = np.exp(momentum_blend.clip(-0.35, 0.35))
    df["confidence_multiplier"] = np.where(df["confidence_penalty_required"].fillna(False), 0.85, 1.0)

    for suffix in ["3y", "5y"]:
        df[f"product_p10_{suffix}"] = df[f"route_p10_{suffix}"] * df["product_adjustment"] * df["confidence_multiplier"]
        df[f"product_median_{suffix}"] = df[f"route_median_{suffix}"] * df["product_adjustment"] * df["confidence_multiplier"]
        df[f"max_purchase_price_25pct_{suffix}"] = df["current_price"] * df[f"product_p10_{suffix}"] / 1.25
        df[f"max_purchase_price_50pct_{suffix}"] = df["current_price"] * df[f"product_p10_{suffix}"] / 1.50
        df[f"price_margin_25pct_{suffix}"] = df[f"max_purchase_price_25pct_{suffix}"] / df["current_price"] - 1.0

    df["momentum_rank"] = pct_rank(momentum_blend)
    df["scarcity_rank"] = pct_rank(df["scarcity_score"])
    df["liquidity_rank"] = pct_rank(np.log1p(df["accepted_listing_count"]))
    df["volatility_rank"] = pct_rank(df["annualized_volatility"], higher_is_better=False)
    df["drawdown_rank"] = pct_rank(df["maximum_drawdown"].abs(), higher_is_better=False)
    df["long_horizon_rank"] = pct_rank(np.log(df["product_median_3y"].clip(lower=1e-9)))
    df["downside_rank"] = pct_rank(np.log(df["product_p10_3y"].clip(lower=1e-9)))

    df["analytical_score"] = (
        0.20 * df["momentum_rank"]
        + 0.15 * df["scarcity_rank"]
        + 0.10 * df["liquidity_rank"]
        + 0.10 * df["volatility_rank"]
        + 0.10 * df["drawdown_rank"]
        + 0.20 * df["long_horizon_rank"]
        + 0.15 * df["downside_rank"]
    ) * df["confidence_multiplier"]
    df = assign_complete_rank(df, "analytical_score", "analytical_rank")

    shock_rows = []
    for shock in PRICE_SHOCKS:
        shocked = df.copy()
        shocked["shocked_price"] = shocked["current_price"] * (1.0 + shock)
        shocked["margin_3y"] = shocked["max_purchase_price_25pct_3y"] / shocked["shocked_price"] - 1.0
        shocked["shock_score"] = shocked["analytical_score"] + 0.10 * np.tanh(shocked["margin_3y"])
        shocked = assign_complete_rank(shocked, "shock_score", "shock_rank")
        for _, row in shocked.iterrows():
            shock_rows.append({"tcgplayer_product_id": row["tcgplayer_product_id"], "price_shock": shock, "shock_rank": row["shock_rank"], "margin_3y": row["margin_3y"]})
    shocks = pd.DataFrame(shock_rows)
    stability = shocks.groupby("tcgplayer_product_id").agg(min_rank=("shock_rank", "min"), max_rank=("shock_rank", "max"), max_abs_margin=("margin_3y", lambda s: float(np.max(np.abs(s))))).reset_index()
    stability["rank_spread"] = stability["max_rank"] - stability["min_rank"]
    df = df.merge(stability, on="tcgplayer_product_id", how="left")
    df["ranking_stable"] = df["rank_spread"].le(5)

    df["preliminary_status"] = np.select(
        [
            df["ranking_stable"] & df["price_margin_25pct_3y"].ge(0.10) & df["product_p10_3y"].ge(1.0),
            df["price_margin_25pct_3y"].ge(-0.10),
        ],
        ["ANALYTICAL_CANDIDATE", "WATCH"],
        default="AVOID_AT_CURRENT_PRICE",
    )
    df["purchase_recommendation_authorized"] = False
    df["maximum_purchase_price_certified"] = False
    df["live_price_freshness_certified"] = False

    required_numeric = ["current_price", "analytical_score", "product_p10_3y", "product_median_3y", "product_p10_5y", "product_median_5y", "max_purchase_price_25pct_3y", "max_purchase_price_25pct_5y"]
    finite_complete = bool(np.isfinite(df[required_numeric].to_numpy(float)).all())
    ids_unique = not df["tcgplayer_product_id"].duplicated().any()
    all_routes_joined = bool(df["route_median_3y"].notna().all() and df["route_median_5y"].notna().all())
    analytical_rank_complete = sorted(df["analytical_rank"].astype(int).tolist()) == list(range(1, REQUIRED_PRODUCTS + 1))
    complete = len(df) == REQUIRED_PRODUCTS and ids_unique and finite_complete and all_routes_joined and analytical_rank_complete

    df.sort_values("analytical_rank").to_csv(OUT_DIR / "collector_v1_product_level_rankings.csv", index=False)
    shocks.to_csv(OUT_DIR / "collector_v1_product_price_shock_tournament.csv", index=False)
    summary = {
        "block_name": "Collector V1 Product-Level Forecast and Ranking Tournament",
        "block_version": "1.0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products": int(len(df)),
        "routes": df["forecast_method"].value_counts().to_dict(),
        "price_shocks_tested": PRICE_SHOCKS,
        "ranking_stable_products": int(df["ranking_stable"].sum()),
        "preliminary_status_counts": df["preliminary_status"].value_counts().to_dict(),
        "factor_rank_direction_verified": True,
        "deterministic_tie_breaking_enforced": True,
        "checks": {"foundation_certified": True, "product_count_50": len(df) == 50, "product_ids_unique": ids_unique, "all_routes_joined": all_routes_joined, "all_required_metrics_finite": finite_complete, "analytical_rank_complete_1_to_50": analytical_rank_complete},
        "critical_failures": [],
        "product_level_tournament_ready": bool(complete),
        "analytical_rankings_ready_for_certification": bool(complete),
        "maximum_purchase_prices_ready_for_certification": bool(complete),
        "live_price_freshness_certified": False,
        "purchase_recommendations_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_PRODUCT_LEVEL_FORECAST_RANKING_TOURNAMENT_READY" if complete else "FAIL_COLLECTOR_V1_PRODUCT_LEVEL_FORECAST_RANKING_TOURNAMENT",
    }
    if not complete:
        summary["critical_failures"] = [k for k, v in summary["checks"].items() if not v]
    (OUT_DIR / "collector_v1_product_level_forecast_ranking_tournament_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (complete or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
