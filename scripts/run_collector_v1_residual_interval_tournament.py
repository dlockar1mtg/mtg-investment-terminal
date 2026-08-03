from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_pre_recommendation_tournament_foundation"
EXPANDED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"
COHORT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_cohort_fallback_tournament"
WINNER_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_short_horizon_winners"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"
METHODS = [
    "GLOBAL_EMPIRICAL",
    "ROUTE_HORIZON_EMPIRICAL",
    "ROUTE_HORIZON_RECENCY_WEIGHTED",
    "SIGNED_CONFORMAL",
    "ABSOLUTE_CONFORMAL",
    "HYBRID_ROUTE_CONFORMAL",
]
LEVELS = [0.80, 0.90]


def first_col(df: pd.DataFrame, names: list[str], required: bool = True) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    if required:
        raise ValueError(f"Required column missing. candidates={names}; available={list(df.columns)}")
    return None


def weighted_quantile(values: np.ndarray, quantile: float, weights: np.ndarray | None = None) -> float:
    values = np.asarray(values, dtype=float)
    mask = np.isfinite(values)
    values = values[mask]
    if values.size == 0:
        return float("nan")
    if weights is None:
        return float(np.quantile(values, quantile))
    weights = np.asarray(weights, dtype=float)[mask]
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    if cumulative[-1] <= 0:
        return float(np.quantile(values, quantile))
    cutoff = quantile * cumulative[-1]
    return float(values[np.searchsorted(cumulative, cutoff, side="left")])


def normalize_expanded(df: pd.DataFrame) -> pd.DataFrame:
    product = first_col(df, ["tcgplayer_product_id", "product_id", "target_product_id"])
    route = first_col(df, ["tournament_lane", "route", "forecast_route"])
    horizon = first_col(df, ["horizon_days", "forecast_horizon_days", "horizon"])
    pred = first_col(df, ["prediction_corrected", "corrected_prediction", "predicted_value", "prediction", "predicted_price", "y_pred"])
    actual = first_col(df, ["actual_value", "actual_price", "actual", "y_true", "target_value"])
    model = first_col(df, ["model_variant", "scarcity_variant", "variant"], required=False)
    date = first_col(df, ["cutoff_date", "as_of_date", "prediction_date", "target_date"], required=False)
    out = pd.DataFrame({
        "product_id": df[product].astype(str),
        "route": df[route].astype(str),
        "horizon_days": pd.to_numeric(df[horizon], errors="coerce"),
        "predicted": pd.to_numeric(df[pred], errors="coerce"),
        "actual": pd.to_numeric(df[actual], errors="coerce"),
        "model_variant": df[model].astype(str) if model else "",
        "observation_date": pd.to_datetime(df[date], errors="coerce") if date else pd.NaT,
        "source_authority": "EXPANDED_PRICE_PREDICTIONS",
    })
    return out.dropna(subset=["horizon_days", "predicted", "actual"])


def normalize_cohort(df: pd.DataFrame) -> pd.DataFrame:
    product = first_col(df, ["tcgplayer_product_id", "product_id", "target_product_id"])
    age = first_col(df, ["age_months", "release_age_months"])
    pred = first_col(df, ["predicted_return", "prediction", "y_pred", "predicted_value"])
    actual = first_col(df, ["actual_return_365d_from_release", "return_365d", "actual_return", "y_true", "actual_value"])
    model = first_col(df, ["model_variant", "variant"])
    date = first_col(df, ["feature_cutoff_date", "cutoff_date", "as_of_date"], required=False)
    out = pd.DataFrame({
        "product_id": df[product].astype(str),
        "route": "EARLY_OPPORTUNITY_COHORT_FALLBACK",
        "horizon_days": 365,
        "predicted": pd.to_numeric(df[pred], errors="coerce"),
        "actual": pd.to_numeric(df[actual], errors="coerce"),
        "model_variant": df[model].astype(str),
        "age_months": pd.to_numeric(df[age], errors="coerce"),
        "observation_date": pd.to_datetime(df[date], errors="coerce") if date else pd.NaT,
        "source_authority": "EARLY_COHORT_FALLBACK_PREDICTIONS",
    })
    return out.dropna(subset=["predicted", "actual", "age_months"])


def calibration_bounds(cal: pd.DataFrame, method: str, level: float, route: str, horizon: int, obs_date: pd.Timestamp | pd.NaT) -> tuple[float, float, int]:
    alpha = 1.0 - level
    global_resid = cal["residual"].to_numpy(float)
    route_frame = cal[(cal["route"] == route) & (cal["horizon_days"] == horizon)]
    if len(route_frame) < 20:
        route_frame = cal[cal["route"] == route]
    if len(route_frame) < 20:
        route_frame = cal
    resid = route_frame["residual"].to_numpy(float)
    if method == "GLOBAL_EMPIRICAL":
        return weighted_quantile(global_resid, alpha / 2), weighted_quantile(global_resid, 1 - alpha / 2), len(global_resid)
    if method == "ROUTE_HORIZON_EMPIRICAL":
        return weighted_quantile(resid, alpha / 2), weighted_quantile(resid, 1 - alpha / 2), len(resid)
    if method == "ROUTE_HORIZON_RECENCY_WEIGHTED":
        dates = route_frame["observation_date"]
        if dates.notna().any() and pd.notna(obs_date):
            age_days = (pd.Timestamp(obs_date) - dates).dt.days.clip(lower=0).fillna(3650).to_numpy(float)
            weights = np.exp(-age_days / 730.0)
        else:
            weights = np.ones(len(route_frame), dtype=float)
        return weighted_quantile(resid, alpha / 2, weights), weighted_quantile(resid, 1 - alpha / 2, weights), len(resid)
    if method == "SIGNED_CONFORMAL":
        return weighted_quantile(resid, alpha / 2), weighted_quantile(resid, 1 - alpha / 2), len(resid)
    if method == "ABSOLUTE_CONFORMAL":
        q = weighted_quantile(np.abs(resid), level)
        return -q, q, len(resid)
    route_low = weighted_quantile(resid, alpha / 2)
    route_high = weighted_quantile(resid, 1 - alpha / 2)
    abs_q = weighted_quantile(np.abs(global_resid), level)
    return min(route_low, -abs_q), max(route_high, abs_q), len(resid)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    foundation = json.loads((FOUNDATION_DIR / "collector_v1_pre_recommendation_tournament_foundation_summary.json").read_text(encoding="utf-8"))
    if foundation.get("residual_interval_tournament_authorized") is not True:
        raise RuntimeError("Certified foundation does not authorize residual interval tournament")

    expanded = normalize_expanded(pd.read_csv(EXPANDED_DIR / "collector_v1_expanded_price_predictions.csv"))
    cohort = normalize_cohort(pd.read_csv(COHORT_DIR / "collector_v1_early_cohort_fallback_predictions.csv"))
    manifest = pd.read_csv(WINNER_DIR / "collector_v1_final_short_horizon_winner_manifest.csv")

    selected_parts: list[pd.DataFrame] = []
    for _, win in manifest.iterrows():
        route = str(win["resolved_route"])
        horizon = int(float(win["horizon_days"]))
        model = str(win.get("resolved_model_variant", ""))
        if route == "EARLY_OPPORTUNITY_COHORT_FALLBACK":
            part = cohort[(cohort["model_variant"] == model) & (cohort["age_months"] == float(win.get("age_months", 1)))]
        else:
            part = expanded[(expanded["route"] == route) & (expanded["horizon_days"] == horizon)]
            if model and "model_variant" in part.columns and part["model_variant"].notna().any():
                model_part = part[part["model_variant"] == model]
                if not model_part.empty:
                    part = model_part
        if not part.empty:
            selected_parts.append(part.copy())
    evidence = pd.concat(selected_parts, ignore_index=True).drop_duplicates()
    evidence["residual"] = evidence["actual"] - evidence["predicted"]
    evidence.to_csv(OUT_DIR / "collector_v1_residual_interval_evidence.csv", index=False)

    detail_rows: list[dict] = []
    for idx, row in evidence.iterrows():
        cal = evidence[evidence["product_id"] != row["product_id"]]
        for method in METHODS:
            for level in LEVELS:
                low_r, high_r, cal_rows = calibration_bounds(cal, method, level, str(row["route"]), int(row["horizon_days"]), row["observation_date"])
                lower = float(row["predicted"] + low_r)
                upper = float(row["predicted"] + high_r)
                actual = float(row["actual"])
                detail_rows.append({
                    "evidence_row": idx,
                    "product_id": row["product_id"],
                    "route": row["route"],
                    "horizon_days": int(row["horizon_days"]),
                    "method": method,
                    "interval_level": level,
                    "predicted": float(row["predicted"]),
                    "actual": actual,
                    "lower": lower,
                    "upper": upper,
                    "covered": lower <= actual <= upper,
                    "lower_miss": actual < lower,
                    "upper_miss": actual > upper,
                    "interval_width": upper - lower,
                    "calibration_rows": cal_rows,
                    "product_holdout_enforced": True,
                })
    details = pd.DataFrame(detail_rows)
    details.to_csv(OUT_DIR / "collector_v1_residual_interval_predictions.csv", index=False)

    metric_rows: list[dict] = []
    group_cols = ["route", "horizon_days", "method", "interval_level"]
    for keys, group in details.groupby(group_cols, dropna=False):
        route, horizon, method, level = keys
        coverage = float(group["covered"].mean())
        width = float(group["interval_width"].mean())
        lower_miss = float(group["lower_miss"].mean())
        upper_miss = float(group["upper_miss"].mean())
        target = float(level)
        tolerance = 0.06 if target == 0.80 else 0.05
        coverage_pass = abs(coverage - target) <= tolerance or (target <= coverage <= target + 0.08)
        tail_limit = (1 - target) * 0.75
        tail_pass = lower_miss <= tail_limit and upper_miss <= tail_limit
        sharpness_score = width / max(float(group["actual"].abs().median()), 1e-9)
        promotable = bool(len(group) >= 20 and coverage_pass and tail_pass and width > 0)
        selection_score = abs(coverage - target) * 10 + sharpness_score + lower_miss + upper_miss
        metric_rows.append({
            "route": route,
            "horizon_days": int(horizon),
            "method": method,
            "interval_level": target,
            "rows": len(group),
            "products": group["product_id"].nunique(),
            "coverage": coverage,
            "target_coverage": target,
            "coverage_error": coverage - target,
            "mean_interval_width": width,
            "normalized_width": sharpness_score,
            "lower_tail_miss_rate": lower_miss,
            "upper_tail_miss_rate": upper_miss,
            "coverage_pass": coverage_pass,
            "tail_balance_pass": tail_pass,
            "promotable": promotable,
            "selection_score": selection_score,
        })
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(OUT_DIR / "collector_v1_residual_interval_metrics.csv", index=False)

    winners: list[pd.Series] = []
    for _, group in metrics.groupby(["route", "horizon_days", "interval_level"], dropna=False):
        promotable = group[group["promotable"]]
        chosen = (promotable if not promotable.empty else group).sort_values(["promotable", "selection_score"], ascending=[False, True]).iloc[0].copy()
        chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_METHOD_MEETS_GATES"
        winners.append(chosen)
    winner_df = pd.DataFrame(winners)
    winner_df.to_csv(OUT_DIR / "collector_v1_residual_interval_winners.csv", index=False)

    unresolved = int((winner_df["promotion_status"] != "PROMOTABLE").sum())
    summary = {
        "block_name": "Collector V1 Residual and Prediction Interval Tournament",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "historical_evidence_rows": int(len(evidence)),
        "historical_products": int(evidence["product_id"].nunique()),
        "routes": sorted(evidence["route"].unique().tolist()),
        "methods_tested": METHODS,
        "interval_levels": LEVELS,
        "candidate_metric_cells": int(len(metrics)),
        "winner_cells": int(len(winner_df)),
        "promoted_winner_cells": int((winner_df["promotion_status"] == "PROMOTABLE").sum()),
        "unresolved_winner_cells": unresolved,
        "product_holdout_enforced": True,
        "residual_interval_tournament_ready": True,
        "residual_interval_tournament_certification_authorized": unresolved == 0,
        "long_horizon_simulation_tournament_authorized_after_certification": unresolved == 0,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_READY" if unresolved == 0 else "PARTIAL_COLLECTOR_V1_RESIDUAL_INTERVAL_TOURNAMENT_READY",
    }
    (OUT_DIR / "collector_v1_residual_interval_tournament_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (unresolved == 0 or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
