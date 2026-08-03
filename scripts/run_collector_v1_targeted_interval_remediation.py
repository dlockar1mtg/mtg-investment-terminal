from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_interval_remediation"


def finite_quantile(values: np.ndarray, q: float) -> float:
    values = np.sort(np.asarray(values, dtype=float))
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    rank = int(np.ceil((values.size + 1) * q)) - 1
    return float(values[min(max(rank, 0), values.size - 1)])


def bounds(cal: pd.DataFrame, method: str, level: float, route: str, horizon: int) -> tuple[float, float, int]:
    alpha = 1.0 - level
    global_resid = cal["residual"].to_numpy(float)
    route_frame = cal[(cal["route"] == route) & (cal["horizon_days"] == horizon)]
    if len(route_frame) < 20:
        route_frame = cal[cal["route"] == route]
    if len(route_frame) < 20:
        route_frame = cal
    route_resid = route_frame["residual"].to_numpy(float)

    if method == "ASYMMETRIC_FINITE_SAMPLE_CONFORMAL":
        return finite_quantile(route_resid, alpha / 2), finite_quantile(route_resid, 1 - alpha / 2), len(route_resid)
    if method == "SHRUNK_ROUTE_GLOBAL_CONFORMAL":
        route_low = finite_quantile(route_resid, alpha / 2)
        route_high = finite_quantile(route_resid, 1 - alpha / 2)
        global_low = finite_quantile(global_resid, alpha / 2)
        global_high = finite_quantile(global_resid, 1 - alpha / 2)
        weight = min(0.80, len(route_resid) / (len(route_resid) + 40.0))
        return weight * route_low + (1 - weight) * global_low, weight * route_high + (1 - weight) * global_high, len(route_resid)
    if method.startswith("INFLATED_ABSOLUTE_CONFORMAL_"):
        factor = float(method.rsplit("_", 1)[1])
        q = finite_quantile(np.abs(route_resid), level)
        return -q * factor, q * factor, len(route_resid)
    raise ValueError(method)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    evidence = pd.read_csv(BASE_DIR / "collector_v1_residual_interval_evidence.csv")
    evidence["residual"] = pd.to_numeric(evidence["actual"], errors="coerce") - pd.to_numeric(evidence["predicted"], errors="coerce")
    winners = pd.read_csv(BASE_DIR / "collector_v1_residual_interval_winners.csv")
    blocked = winners[winners["promotion_status"] != "PROMOTABLE"].copy()
    if len(blocked) != 1:
        raise RuntimeError(f"Expected exactly one blocked interval cell, found {len(blocked)}")

    blocked_row = blocked.iloc[0]
    route = str(blocked_row["route"])
    horizon = int(float(blocked_row["horizon_days"]))
    level = float(blocked_row["interval_level"])
    target = evidence[(evidence["route"] == route) & (evidence["horizon_days"] == horizon)].copy()
    if target.empty:
        raise RuntimeError("Blocked cell has no historical evidence rows")

    methods = [
        "ASYMMETRIC_FINITE_SAMPLE_CONFORMAL",
        "SHRUNK_ROUTE_GLOBAL_CONFORMAL",
        "INFLATED_ABSOLUTE_CONFORMAL_1.05",
        "INFLATED_ABSOLUTE_CONFORMAL_1.10",
        "INFLATED_ABSOLUTE_CONFORMAL_1.15",
        "INFLATED_ABSOLUTE_CONFORMAL_1.20",
        "INFLATED_ABSOLUTE_CONFORMAL_1.30",
        "INFLATED_ABSOLUTE_CONFORMAL_1.40",
        "INFLATED_ABSOLUTE_CONFORMAL_1.50",
    ]

    detail_rows: list[dict] = []
    for idx, row in target.iterrows():
        cal = evidence[evidence["product_id"].astype(str) != str(row["product_id"])]
        for method in methods:
            low_r, high_r, cal_rows = bounds(cal, method, level, route, horizon)
            lower = float(row["predicted"] + low_r)
            upper = float(row["predicted"] + high_r)
            actual = float(row["actual"])
            detail_rows.append({
                "evidence_row": idx,
                "product_id": row["product_id"],
                "route": route,
                "horizon_days": horizon,
                "interval_level": level,
                "method": method,
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
    details.to_csv(OUT_DIR / "collector_v1_targeted_interval_predictions.csv", index=False)

    metric_rows: list[dict] = []
    for method, group in details.groupby("method"):
        coverage = float(group["covered"].mean())
        width = float(group["interval_width"].mean())
        lower_miss = float(group["lower_miss"].mean())
        upper_miss = float(group["upper_miss"].mean())
        tolerance = 0.06 if level == 0.80 else 0.05
        coverage_pass = abs(coverage - level) <= tolerance or (level <= coverage <= level + 0.08)
        tail_limit = (1 - level) * 0.75
        tail_pass = lower_miss <= tail_limit and upper_miss <= tail_limit
        normalized_width = width / max(float(group["actual"].abs().median()), 1e-9)
        promotable = bool(len(group) >= 20 and coverage_pass and tail_pass and width > 0)
        metric_rows.append({
            "route": route,
            "horizon_days": horizon,
            "interval_level": level,
            "method": method,
            "rows": len(group),
            "products": group["product_id"].nunique(),
            "coverage": coverage,
            "target_coverage": level,
            "coverage_error": coverage - level,
            "mean_interval_width": width,
            "normalized_width": normalized_width,
            "lower_tail_miss_rate": lower_miss,
            "upper_tail_miss_rate": upper_miss,
            "coverage_pass": coverage_pass,
            "tail_balance_pass": tail_pass,
            "promotable": promotable,
            "selection_score": abs(coverage - level) * 10 + normalized_width + lower_miss + upper_miss,
        })
    metrics = pd.DataFrame(metric_rows).sort_values(["promotable", "selection_score"], ascending=[False, True])
    metrics.to_csv(OUT_DIR / "collector_v1_targeted_interval_metrics.csv", index=False)

    promotable = metrics[metrics["promotable"]]
    chosen = (promotable if not promotable.empty else metrics).iloc[0].copy()
    chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_TARGETED_METHOD_MEETS_GATES"
    winner = pd.DataFrame([chosen])
    winner.to_csv(OUT_DIR / "collector_v1_targeted_interval_winner.csv", index=False)

    resolved = str(chosen["promotion_status"]) == "PROMOTABLE"
    consolidated = winners.copy()
    mask = ((consolidated["route"] == route) & (consolidated["horizon_days"].astype(float) == horizon) & (consolidated["interval_level"].astype(float) == level))
    for col in winner.columns:
        if col not in consolidated.columns:
            consolidated[col] = np.nan
        consolidated.loc[mask, col] = chosen[col]
    consolidated.to_csv(OUT_DIR / "collector_v1_consolidated_residual_interval_winners.csv", index=False)

    unresolved = int((consolidated["promotion_status"] != "PROMOTABLE").sum())
    summary = {
        "block_name": "Collector V1 Targeted Interval Remediation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blocked_route": route,
        "blocked_horizon_days": horizon,
        "blocked_interval_level": level,
        "targeted_methods_tested": methods,
        "historical_rows": int(len(target)),
        "historical_products": int(target["product_id"].nunique()),
        "targeted_cell_resolved": resolved,
        "selected_method": str(chosen["method"]),
        "selected_coverage": float(chosen["coverage"]),
        "selected_lower_tail_miss_rate": float(chosen["lower_tail_miss_rate"]),
        "selected_upper_tail_miss_rate": float(chosen["upper_tail_miss_rate"]),
        "consolidated_winner_cells": int(len(consolidated)),
        "consolidated_unresolved_cells": unresolved,
        "product_holdout_enforced": True,
        "residual_interval_stack_complete": unresolved == 0,
        "long_horizon_simulation_tournament_authorized_after_certification": unresolved == 0,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_TARGETED_INTERVAL_REMEDIATION_READY" if unresolved == 0 else "PARTIAL_COLLECTOR_V1_TARGETED_INTERVAL_REMEDIATION_READY",
    }
    (OUT_DIR / "collector_v1_targeted_interval_remediation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (unresolved == 0 or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
