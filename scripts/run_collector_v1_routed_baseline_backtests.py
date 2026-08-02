from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_v1_experiment_foundation"
EXPERIMENTS = BASE / "collector_v1_historical_cutoff_experiments.csv"
SSI = BASE / "collector_supply_scarcity_index_v1a.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_baseline_backtests"


def smape(actual: pd.Series, pred: pd.Series) -> float:
    denom = (actual.abs() + pred.abs()).replace(0, np.nan)
    return float((2 * (actual - pred).abs() / denom).mean())


def metrics(group: pd.DataFrame) -> dict:
    actual = group["actual_future_price"].astype(float)
    pred = group["predicted_price"].astype(float)
    error = pred - actual
    pct = error.abs() / actual.replace(0, np.nan)
    actual_ret = group["actual_return"].astype(float)
    pred_ret = group["predicted_return"].astype(float)
    return {
        "rows": int(len(group)),
        "mae": float(error.abs().mean()),
        "mape": float(pct.mean()),
        "median_ape": float(pct.median()),
        "smape": smape(actual, pred),
        "rmse": float(np.sqrt((error.pow(2)).mean())),
        "bias": float(error.mean()),
        "directional_accuracy": float((np.sign(actual_ret) == np.sign(pred_ret)).mean()),
    }


def predict(df: pd.DataFrame, variant: str) -> pd.Series:
    months = df["horizon_months"].astype(float)
    mom3 = pd.to_numeric(df["momentum_3m"], errors="coerce").fillna(0)
    mom12 = pd.to_numeric(df["momentum_12m"], errors="coerce").fillna(mom3)
    trend = pd.to_numeric(df["trend_slope_monthly_at_cutoff"], errors="coerce").fillna(0)
    route = df["forecast_method"].astype(str)

    direct = route.str.contains("DIRECT_HISTORY", na=False)
    base_monthly = np.where(direct, 0.50 * trend + 0.30 * (mom3 / 3) + 0.20 * (mom12 / 12), 0.35 * trend + 0.25 * (mom3 / 3) + 0.40 * (mom12 / 12))
    base_monthly = pd.Series(base_monthly, index=df.index).clip(-0.15, 0.15)

    if variant == "NO_SCARCITY":
        adjustment = 0.0
    elif variant == "SSI_V1A":
        scarcity = pd.to_numeric(df["supply_scarcity_index_v1a"], errors="coerce").fillna(50)
        adjustment = ((scarcity - 50) / 50) * 0.005
    else:
        scarcity = pd.to_numeric(df.get("supply_scarcity_index_v1", pd.Series(50, index=df.index)), errors="coerce").fillna(50)
        adjustment = ((scarcity - 50) / 50) * 0.005

    monthly = (base_monthly + adjustment).clip(-0.15, 0.15)
    return (1 + monthly).pow(months) - 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if not EXPERIMENTS.exists() or not SSI.exists():
        raise FileNotFoundError("Experiment foundation outputs are missing.")

    exp = pd.read_csv(EXPERIMENTS, low_memory=False)
    ssi = pd.read_csv(SSI, low_memory=False)
    exp["tcgplayer_product_id"] = exp["tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    ssi["tcgplayer_product_id"] = ssi["tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    joined = exp.merge(ssi[["tcgplayer_product_id", "supply_scarcity_index_v1a"]], on="tcgplayer_product_id", how="left")

    prediction_frames = []
    for variant in ["NO_SCARCITY", "SSI_V1A"]:
        frame = joined.copy()
        frame["model_variant"] = variant
        frame["predicted_return"] = predict(frame, variant)
        frame["predicted_price"] = frame["price_at_cutoff"].astype(float) * (1 + frame["predicted_return"])
        prediction_frames.append(frame)
    predictions = pd.concat(prediction_frames, ignore_index=True)

    metric_rows = []
    group_cols = ["model_variant", "forecast_method", "horizon_days"]
    for keys, group in predictions.groupby(group_cols):
        row = dict(zip(group_cols, keys))
        row.update(metrics(group))
        metric_rows.append(row)
    metrics_df = pd.DataFrame(metric_rows)

    overall_rows = []
    for variant, group in predictions.groupby("model_variant"):
        row = {"model_variant": variant}
        row.update(metrics(group))
        overall_rows.append(row)
    overall = pd.DataFrame(overall_rows)

    blockers = []
    if predictions.empty:
        blockers.append("No baseline predictions were generated.")
    if metrics_df.empty:
        blockers.append("No grouped backtest metrics were generated.")
    if not predictions["feature_cutoff_enforced"].astype(bool).all() or not predictions["target_after_cutoff"].astype(bool).all():
        blockers.append("Anti-leakage checks failed in backtest inputs.")
    if predictions["actual_future_price"].isna().any() or predictions["predicted_price"].isna().any():
        blockers.append("Backtest contains missing actual or predicted prices.")

    predictions.to_csv(OUT / "collector_v1_baseline_predictions.csv", index=False)
    metrics_df.to_csv(OUT / "collector_v1_baseline_metrics_by_route_horizon.csv", index=False)
    overall.to_csv(OUT / "collector_v1_baseline_metrics_overall.csv", index=False)

    best_variant = None
    if not overall.empty:
        best_variant = str(overall.sort_values(["smape", "mae"]).iloc[0]["model_variant"])
    summary = {
        "block_name": "Collector V1 Routed Baseline Backtests",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_rows": int(len(predictions)),
        "products": int(predictions["tcgplayer_product_id"].nunique()) if not predictions.empty else 0,
        "routes": sorted(predictions["forecast_method"].dropna().astype(str).unique().tolist()) if not predictions.empty else [],
        "horizons": sorted(int(x) for x in predictions["horizon_days"].dropna().unique()) if not predictions.empty else [],
        "variants": sorted(predictions["model_variant"].unique().tolist()) if not predictions.empty else [],
        "best_baseline_variant_by_smape_then_mae": best_variant,
        "anti_leakage_pass": not any("Anti-leakage" in b for b in blockers),
        "blockers": blockers,
        "baseline_backtests_ready": not blockers,
        "model_selection_authorized": not blockers,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_ROUTED_BASELINE_BACKTESTS" if not blockers else "BLOCKED_COLLECTOR_V1_ROUTED_BASELINE_BACKTESTS",
    }
    (OUT / "collector_v1_baseline_backtest_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
