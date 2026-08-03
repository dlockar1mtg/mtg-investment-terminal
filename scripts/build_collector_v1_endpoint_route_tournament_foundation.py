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
OUT = ROOT / "data/governance/permanence/certification/collector_v1_endpoint_route_tournament_foundation"
OUT.mkdir(parents=True, exist_ok=True)

BASELINE_METRICS = BASELINE_DIR / "collector_v1_baseline_metrics_by_route_horizon.csv"
EARLY_METRICS = EARLY_DIR / "collector_v1_early_opportunity_tournament_metrics.csv"
EARLY_WINNERS = EARLY_DIR / "collector_v1_early_opportunity_winners_by_age.csv"
SUMMARY_PATH = OUT / "collector_v1_endpoint_route_tournament_foundation_summary.json"
CELL_PATH = OUT / "collector_v1_tournament_cells.csv"
PROMOTION_PATH = OUT / "collector_v1_promotion_matrix.csv"
GAP_PATH = OUT / "collector_v1_tournament_gap_register.csv"

PRIMARY_HORIZONS = [90, 180, 365]
LONG_HORIZONS = [1095, 1825]
MIN_ROWS_BY_HORIZON = {90: 60, 180: 50, 365: 40}
MIN_EARLY_ROWS = 30
MAX_ABS_BIAS = 0.20
MIN_EARLY_RECALL = 0.50
MAX_EARLY_FPR = 0.40
MIN_TOP_PRECISION = 0.60


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    missing = [str(p) for p in [BASELINE_METRICS, EARLY_METRICS, EARLY_WINNERS] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Required certified tournament inputs missing: {missing}")

    baseline = pd.read_csv(BASELINE_METRICS, low_memory=False)
    early = pd.read_csv(EARLY_METRICS, low_memory=False)
    winners = pd.read_csv(EARLY_WINNERS, low_memory=False)

    for c in ["horizon_days", "rows", "mae", "mape", "median_ape", "smape", "rmse", "bias", "directional_accuracy"]:
        if c in baseline.columns:
            baseline[c] = to_num(baseline[c])
    for c in ["age_months", "rows", "mae", "rmse", "bias", "rank_correlation", "top_quintile_precision_25pct", "winner_recall_25pct", "false_positive_rate", "selection_score"]:
        if c in early.columns:
            early[c] = to_num(early[c])

    baseline = baseline[baseline["horizon_days"].isin(PRIMARY_HORIZONS)].copy()
    baseline["tournament_lane"] = baseline["forecast_method"]
    baseline["selection_objective"] = "PRICE_FORECAST"
    baseline["minimum_rows_required"] = baseline["horizon_days"].map(MIN_ROWS_BY_HORIZON)
    baseline["row_count_pass"] = baseline["rows"] >= baseline["minimum_rows_required"]
    baseline["bias_pass"] = baseline["bias"].abs() <= np.maximum(25.0, baseline["mae"] * 0.50)
    baseline["candidate_promotable"] = baseline["row_count_pass"] & baseline["bias_pass"]

    baseline_cells = baseline[[
        "tournament_lane", "horizon_days", "model_variant", "selection_objective",
        "rows", "mae", "rmse", "bias", "smape", "directional_accuracy",
        "minimum_rows_required", "row_count_pass", "bias_pass", "candidate_promotable"
    ]].copy()
    baseline_cells["age_months"] = pd.NA
    baseline_cells["rank_correlation"] = pd.NA
    baseline_cells["top_quintile_precision_25pct"] = pd.NA
    baseline_cells["winner_recall_25pct"] = pd.NA
    baseline_cells["false_positive_rate"] = pd.NA

    early["tournament_lane"] = "EARLY_OPPORTUNITY_COMPARABLE_TRANSFER"
    early["horizon_days"] = 365
    early["selection_objective"] = "EARLY_WINNER_RANKING"
    early["minimum_rows_required"] = MIN_EARLY_ROWS
    early["row_count_pass"] = early["rows"] >= MIN_EARLY_ROWS
    early["bias_pass"] = early["bias"].abs() <= MAX_ABS_BIAS
    early["precision_pass"] = early["top_quintile_precision_25pct"] >= MIN_TOP_PRECISION
    early["recall_pass"] = early["winner_recall_25pct"] >= MIN_EARLY_RECALL
    early["fpr_pass"] = early["false_positive_rate"] <= MAX_EARLY_FPR
    early["candidate_promotable"] = (
        early["row_count_pass"] & early["bias_pass"] & early["precision_pass"] &
        early["recall_pass"] & early["fpr_pass"]
    )

    early_cells = early[[
        "tournament_lane", "horizon_days", "age_months", "model_variant", "selection_objective",
        "rows", "mae", "rmse", "bias", "rank_correlation", "top_quintile_precision_25pct",
        "winner_recall_25pct", "false_positive_rate", "minimum_rows_required", "row_count_pass",
        "bias_pass", "candidate_promotable"
    ]].copy()
    early_cells["smape"] = pd.NA
    early_cells["directional_accuracy"] = pd.NA

    cells = pd.concat([baseline_cells, early_cells], ignore_index=True, sort=False)

    promotion_rows = []
    for (lane, horizon, objective), g in cells.groupby(["tournament_lane", "horizon_days", "selection_objective"], dropna=False):
        promotable = g[g["candidate_promotable"].astype(bool)].copy()
        if objective == "PRICE_FORECAST":
            ranked = g.sort_values(["smape", "mae", "rmse"], ascending=[True, True, True])
        else:
            ranked = g.sort_values(
                ["top_quintile_precision_25pct", "winner_recall_25pct", "rank_correlation", "mae"],
                ascending=[False, False, False, True],
            )
        winner = ranked.iloc[0]
        promotion_rows.append({
            "tournament_lane": lane,
            "horizon_days": int(horizon),
            "selection_objective": objective,
            "provisional_winner": winner["model_variant"],
            "candidate_count": int(len(g)),
            "promotable_candidate_count": int(len(promotable)),
            "promotion_status": "READY_FOR_EXPANDED_TOURNAMENT" if len(promotable) else "BLOCKED_NEEDS_EXPANDED_TOURNAMENT",
            "reason": "At least one candidate meets provisional gates." if len(promotable) else "No candidate meets row-count, bias, and investment-usefulness gates.",
        })
    promotion = pd.DataFrame(promotion_rows)

    required_price_cells = {(route, h) for route in [
        "DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED", "COMPARABLE_PRODUCT_ADJUSTED"
    ] for h in PRIMARY_HORIZONS}
    observed_price_cells = set(
        zip(
            promotion.loc[promotion["selection_objective"] == "PRICE_FORECAST", "tournament_lane"],
            promotion.loc[promotion["selection_objective"] == "PRICE_FORECAST", "horizon_days"].astype(int),
        )
    )
    missing_price_cells = sorted(required_price_cells - observed_price_cells)

    early_ready_ages = promotion.loc[
        (promotion["selection_objective"] == "EARLY_WINNER_RANKING") &
        (promotion["promotion_status"] == "READY_FOR_EXPANDED_TOURNAMENT"), "horizon_days"
    ]

    gaps = [
        {
            "gap": "expanded_model_families",
            "status": "REQUIRED",
            "action": "Run contract-authorized model families with rolling-origin and product/cohort holdouts.",
            "blocks_production": True,
        },
        {
            "gap": "comparable_similarity_score",
            "status": "NOT_CONNECTED",
            "action": "Connect certified pair-score authority and test similarity-weighted transfer.",
            "blocks_production": True,
        },
        {
            "gap": "early_opportunity_sample_size_and_recall",
            "status": "INSUFFICIENT_FOR_PROMOTION" if not len(early_ready_ages) else "PROVISIONALLY_READY",
            "action": "Increase product/cohort holdouts and require recall >= 0.50 with calibrated bias.",
            "blocks_production": not bool(len(early_ready_ages)),
        },
        {
            "gap": "prediction_interval_calibration",
            "status": "REQUIRED",
            "action": "Calibrate route-horizon residual intervals after winner selection.",
            "blocks_production": True,
        },
        {
            "gap": "long_horizon_simulation",
            "status": "WAITING_ON_SHORT_HORIZON_WINNERS",
            "action": "Run governed 3-year and 5-year simulations only after calibrated 90/180/365 winners.",
            "blocks_production": True,
        },
    ]
    gap_df = pd.DataFrame(gaps)

    blockers = []
    if missing_price_cells:
        blockers.append(f"Missing baseline route-horizon cells: {missing_price_cells}")
    if cells.empty:
        blockers.append("No tournament candidates were assembled.")
    if not bool(cells["candidate_promotable"].any()):
        blockers.append("No candidate meets provisional promotion gates.")

    summary = {
        "block_name": "Collector V1 Endpoint-Route Tournament Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_rows": int(len(cells)),
        "promotion_cells": int(len(promotion)),
        "required_price_cells": int(len(required_price_cells)),
        "observed_price_cells": int(len(observed_price_cells)),
        "missing_price_cells": [list(x) for x in missing_price_cells],
        "early_product_age_rows_per_candidate": int(early["rows"].min()) if not early.empty else 0,
        "early_candidates_promotable": int(early["candidate_promotable"].sum()),
        "price_candidates_promotable": int(baseline["candidate_promotable"].sum()),
        "bias_correction_required": bool((early["bias"].abs() > MAX_ABS_BIAS).any()),
        "expanded_tournament_required": True,
        "prediction_interval_calibration_required": True,
        "long_horizon_simulation_authorized_now": False,
        "blockers": blockers,
        "tournament_foundation_ready": not blockers,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_ENDPOINT_ROUTE_TOURNAMENT_FOUNDATION_READY" if not blockers else "BLOCKED_COLLECTOR_V1_ENDPOINT_ROUTE_TOURNAMENT_FOUNDATION",
    }

    cells.to_csv(CELL_PATH, index=False)
    promotion.to_csv(PROMOTION_PATH, index=False)
    gap_df.to_csv(GAP_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
