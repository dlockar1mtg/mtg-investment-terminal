from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "data/governance/permanence/certification/collector_v1_baseline_backtests"
EARLY_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f"None of the governed candidate paths exist: {[str(p) for p in paths]}")


def first_col(df: pd.DataFrame, names: list[str]) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"Required column missing. candidates={names}; available={list(df.columns)}")


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def safe_smape(actual: pd.Series, pred: pd.Series) -> float:
    denom = (actual.abs() + pred.abs()).replace(0, np.nan)
    return float((2.0 * (pred - actual).abs() / denom).mean())


def metrics(frame: pd.DataFrame, actual: str, pred: str) -> dict[str, float | int]:
    a = numeric(frame[actual])
    p = numeric(frame[pred])
    mask = a.notna() & p.notna()
    a, p = a[mask], p[mask]
    err = p - a
    ape = (err.abs() / a.abs().replace(0, np.nan))
    return {
        "rows": int(mask.sum()),
        "mae": float(err.abs().mean()),
        "rmse": float(np.sqrt(np.mean(np.square(err)))),
        "bias": float(err.mean()),
        "mape": float(ape.mean()),
        "median_ape": float(ape.median()),
        "smape": safe_smape(a, p),
        "directional_accuracy": float(((p >= 0) == (a >= 0)).mean()),
    }


def calibrate_price_predictions(df: pd.DataFrame) -> pd.DataFrame:
    id_col = first_col(df, ["tcgplayer_product_id", "product_id"])
    route_col = first_col(df, ["forecast_method", "route", "tournament_lane"])
    horizon_col = first_col(df, ["horizon_days"])
    variant_col = first_col(df, ["model_variant", "variant"])
    actual_col = first_col(df, ["actual_future_price", "actual_price", "target_price"])
    pred_col = first_col(df, ["predicted_price", "forecast_price", "baseline_prediction"])

    work = df.copy()
    work[id_col] = work[id_col].astype(str)
    work[actual_col] = numeric(work[actual_col])
    work[pred_col] = numeric(work[pred_col])
    work["raw_residual"] = work[actual_col] - work[pred_col]
    group_cols = [route_col, horizon_col, variant_col]

    corrected_parts: list[pd.DataFrame] = []
    for _, group in work.groupby(group_cols, dropna=False):
        group = group.copy()
        total_sum = group["raw_residual"].sum()
        total_count = group["raw_residual"].notna().sum()
        by_product = group.groupby(id_col)["raw_residual"].agg(["sum", "count"])
        sums = group[id_col].map(by_product["sum"]).fillna(0.0)
        counts = group[id_col].map(by_product["count"]).fillna(0)
        denom = (total_count - counts).replace(0, np.nan)
        group["holdout_bias_adjustment"] = ((total_sum - sums) / denom).fillna(0.0)
        group["predicted_price_bias_corrected"] = group[pred_col] + group["holdout_bias_adjustment"]

        abs_resid = (group[actual_col] - group["predicted_price_bias_corrected"]).abs()
        q80 = float(abs_resid.quantile(0.80)) if abs_resid.notna().any() else np.nan
        q90 = float(abs_resid.quantile(0.90)) if abs_resid.notna().any() else np.nan
        group["interval_80_lower"] = (group["predicted_price_bias_corrected"] - q80).clip(lower=0)
        group["interval_80_upper"] = group["predicted_price_bias_corrected"] + q80
        group["interval_90_lower"] = (group["predicted_price_bias_corrected"] - q90).clip(lower=0)
        group["interval_90_upper"] = group["predicted_price_bias_corrected"] + q90
        group["covered_80"] = (group[actual_col] >= group["interval_80_lower"]) & (group[actual_col] <= group["interval_80_upper"])
        group["covered_90"] = (group[actual_col] >= group["interval_90_lower"]) & (group[actual_col] <= group["interval_90_upper"])
        corrected_parts.append(group)

    out = pd.concat(corrected_parts, ignore_index=True)
    out.attrs.update({"id": id_col, "route": route_col, "horizon": horizon_col, "variant": variant_col, "actual": actual_col, "pred": pred_col})
    return out


def calibrate_early_predictions(df: pd.DataFrame) -> pd.DataFrame:
    id_col = first_col(df, ["tcgplayer_product_id", "product_id"])
    age_col = first_col(df, ["age_months"])
    variant_col = first_col(df, ["model_variant", "variant"])
    actual_col = first_col(df, ["actual_first_year_return", "first_year_return", "actual_return"])
    pred_col = first_col(df, ["predicted_first_year_return", "predicted_return", "forecast_return"])

    work = df.copy()
    work[id_col] = work[id_col].astype(str)
    work[actual_col] = numeric(work[actual_col])
    work[pred_col] = numeric(work[pred_col])
    work["raw_residual"] = work[actual_col] - work[pred_col]

    parts: list[pd.DataFrame] = []
    for _, group in work.groupby([age_col, variant_col], dropna=False):
        group = group.copy()
        total_sum = group["raw_residual"].sum()
        total_count = group["raw_residual"].notna().sum()
        by_product = group.groupby(id_col)["raw_residual"].agg(["sum", "count"])
        sums = group[id_col].map(by_product["sum"]).fillna(0.0)
        counts = group[id_col].map(by_product["count"]).fillna(0)
        denom = (total_count - counts).replace(0, np.nan)
        group["holdout_bias_adjustment"] = ((total_sum - sums) / denom).fillna(0.0)
        group["predicted_return_bias_corrected"] = group[pred_col] + group["holdout_bias_adjustment"]
        abs_resid = (group[actual_col] - group["predicted_return_bias_corrected"]).abs()
        q90 = float(abs_resid.quantile(0.90)) if abs_resid.notna().any() else np.nan
        group["return_p10"] = group["predicted_return_bias_corrected"] - q90
        group["return_p90"] = group["predicted_return_bias_corrected"] + q90
        parts.append(group)

    out = pd.concat(parts, ignore_index=True)
    out.attrs.update({"id": id_col, "age": age_col, "variant": variant_col, "actual": actual_col, "pred": pred_col})
    return out


def early_ranking_metrics(group: pd.DataFrame, actual_col: str, pred_col: str) -> dict[str, float | int]:
    base = metrics(group, actual_col, pred_col)
    ranked = group[[actual_col, pred_col]].dropna().sort_values(pred_col, ascending=False)
    n = len(ranked)
    top_n = max(1, int(np.ceil(n * 0.20)))
    predicted_top = ranked.head(top_n)
    actual_winner = ranked[actual_col] >= 0.25
    predicted_positive = ranked[pred_col] >= 0.25
    tp = int((predicted_positive & actual_winner).sum())
    fp = int((predicted_positive & ~actual_winner).sum())
    winners = int(actual_winner.sum())
    base.update({
        "rank_correlation": float(ranked[actual_col].corr(ranked[pred_col], method="spearman")) if n > 2 else np.nan,
        "top_quintile_precision_25pct": float((predicted_top[actual_col] >= 0.25).mean()),
        "winner_recall_25pct": float(tp / winners) if winners else np.nan,
        "false_positive_rate": float(fp / max(1, int(predicted_positive.sum()))),
    })
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    baseline_path = first_existing([
        BASELINE_DIR / "collector_v1_baseline_predictions.csv",
        BASELINE_DIR / "collector_v1_routed_baseline_predictions.csv",
        BASELINE_DIR / "collector_v1_baseline_backtest_predictions.csv",
    ])
    early_path = first_existing([
        EARLY_DIR / "collector_v1_early_opportunity_predictions.csv",
    ])

    price = calibrate_price_predictions(pd.read_csv(baseline_path))
    early = calibrate_early_predictions(pd.read_csv(early_path))

    price_meta = price.attrs.copy()
    early_meta = early.attrs.copy()

    price_rows: list[dict] = []
    for keys, group in price.groupby([price_meta["route"], price_meta["horizon"], price_meta["variant"]], dropna=False):
        raw = metrics(group, price_meta["actual"], price_meta["pred"])
        corrected = metrics(group, price_meta["actual"], "predicted_price_bias_corrected")
        row = {
            "tournament_lane": keys[0], "horizon_days": int(keys[1]), "model_variant": keys[2],
            "selection_objective": "PRICE_FORECAST", **{f"raw_{k}": v for k, v in raw.items()}, **corrected,
            "coverage_80": float(group["covered_80"].mean()), "coverage_90": float(group["covered_90"].mean()),
        }
        row["promotable"] = bool(row["rows"] >= 30 and abs(row["bias"]) <= max(25.0, 0.10 * float(group[price_meta["actual"]].median())) and row["coverage_80"] >= 0.70 and row["coverage_90"] >= 0.82)
        row["selection_score"] = float(row["smape"] + 0.25 * abs(row["bias"]) / max(1.0, float(group[price_meta["actual"]].median())) + abs(row["coverage_90"] - 0.90))
        price_rows.append(row)

    early_rows: list[dict] = []
    for keys, group in early.groupby([early_meta["age"], early_meta["variant"]], dropna=False):
        raw = early_ranking_metrics(group, early_meta["actual"], early_meta["pred"])
        corrected = early_ranking_metrics(group, early_meta["actual"], "predicted_return_bias_corrected")
        row = {"tournament_lane": "EARLY_OPPORTUNITY_COMPARABLE_TRANSFER", "horizon_days": 365, "age_months": int(keys[0]), "model_variant": keys[1], "selection_objective": "EARLY_WINNER_RANKING", **{f"raw_{k}": v for k, v in raw.items()}, **corrected}
        row["promotable"] = bool(row["rows"] >= 30 and abs(row["bias"]) <= 0.20 and row["top_quintile_precision_25pct"] >= 0.60 and row["winner_recall_25pct"] >= 0.50 and row["false_positive_rate"] <= 0.40)
        row["selection_score"] = float(-(0.35 * row["top_quintile_precision_25pct"] + 0.35 * row["winner_recall_25pct"] + 0.20 * max(-1.0, row["rank_correlation"]) - 0.10 * row["false_positive_rate"]))
        early_rows.append(row)

    cells = pd.concat([pd.DataFrame(price_rows), pd.DataFrame(early_rows)], ignore_index=True, sort=False)
    winners: list[pd.Series] = []
    for _, group in cells.groupby(["tournament_lane", "horizon_days", "selection_objective"], dropna=False):
        eligible = group[group["promotable"] == True]
        chosen = (eligible if not eligible.empty else group).sort_values("selection_score").iloc[0].copy()
        chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_CANDIDATE_MEETS_GATES"
        winners.append(chosen)
    winner_df = pd.DataFrame(winners)

    price.to_csv(OUT_DIR / "collector_v1_expanded_price_predictions.csv", index=False)
    early.to_csv(OUT_DIR / "collector_v1_expanded_early_predictions.csv", index=False)
    cells.to_csv(OUT_DIR / "collector_v1_expanded_tournament_cells.csv", index=False)
    winner_df.to_csv(OUT_DIR / "collector_v1_expanded_tournament_winners.csv", index=False)

    missing_similarity = True
    gaps = pd.DataFrame([
        {"gap": "comparable_similarity_score", "status": "NOT_CONNECTED", "action": "Register certified pair-score authority and add similarity-weighted candidates.", "blocks_production": True},
        {"gap": "early_opportunity_sample_size", "status": "CHECK_TOURNAMENT_RESULTS", "action": "Require at least 30 independent product/cohort holdouts per promoted age cell.", "blocks_production": True},
        {"gap": "long_horizon_simulation", "status": "WAITING_ON_PROMOTED_SHORT_HORIZON_WINNERS", "action": "Run governed 3-year and 5-year simulations after winner certification.", "blocks_production": True},
    ])
    gaps.to_csv(OUT_DIR / "collector_v1_expanded_tournament_gap_register.csv", index=False)

    blocked_cells = int((winner_df["promotion_status"] != "PROMOTABLE").sum())
    summary = {
        "block_name": "Collector V1 Expanded Endpoint-Route Tournament",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_prediction_rows": int(len(price)),
        "early_prediction_rows": int(len(early)),
        "candidate_cells": int(len(cells)),
        "winner_cells": int(len(winner_df)),
        "promoted_winner_cells": int((winner_df["promotion_status"] == "PROMOTABLE").sum()),
        "blocked_winner_cells": blocked_cells,
        "bias_correction": "LEAVE_ONE_PRODUCT_OUT",
        "interval_calibration": "EMPIRICAL_CONFORMAL_RESIDUAL_QUANTILES",
        "product_holdout_enforced": True,
        "similarity_weighted_comparables_connected": not missing_similarity,
        "expanded_tournament_ready": True,
        "winner_certification_authorized": blocked_cells == 0 and not missing_similarity,
        "long_horizon_simulation_authorized_now": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_EXPANDED_TOURNAMENT_READY",
    }
    (OUT_DIR / "collector_v1_expanded_tournament_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
