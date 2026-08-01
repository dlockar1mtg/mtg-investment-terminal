from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_replay_phase_2a_v1.json"
FOUNDATION = ROOT / "data/operations/collector_walk_forward_replay_foundation/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"


def load_selected_ledger() -> pd.DataFrame:
    summary = json.loads((FOUNDATION / "collector_walk_forward_replay_foundation_summary.json").read_text(encoding="utf-8"))
    source = ROOT / summary["selected_price_ledger"]
    inventory = pd.read_csv(FOUNDATION / "collector_walk_forward_source_inventory.csv", low_memory=False)
    meta = inventory[inventory["path"] == summary["selected_price_ledger"]].iloc[0]
    raw = pd.read_csv(source, low_memory=False)
    id_col = meta["id_column"] if pd.notna(meta["id_column"]) else None
    name_col = meta["name_column"] if pd.notna(meta["name_column"]) else None
    date_col = str(meta["observation_date_column"])
    knowledge_col = meta["knowledge_date_column"] if pd.notna(meta["knowledge_date_column"]) else None
    price_col = str(meta["price_column"])
    work = pd.DataFrame({
        "product_key": raw[id_col].astype(str) if id_col else raw[name_col].astype(str),
        "product_name": raw[name_col].astype(str) if name_col else raw[id_col].astype(str),
        "observation_date": pd.to_datetime(raw[date_col], errors="coerce", utc=True).dt.tz_localize(None),
        "knowledge_date": pd.to_datetime(raw[knowledge_col], errors="coerce", utc=True).dt.tz_localize(None) if knowledge_col else pd.to_datetime(raw[date_col], errors="coerce", utc=True).dt.tz_localize(None),
        "price": pd.to_numeric(raw[price_col], errors="coerce"),
    }).dropna(subset=["product_key", "product_name", "observation_date", "knowledge_date", "price"])
    return work[work["price"] > 0].copy()


def trailing_return(group: pd.DataFrame, cutoff: pd.Timestamp, days: int) -> float | None:
    g = group[(group["knowledge_date"] <= cutoff) & (group["observation_date"] <= cutoff)].sort_values("observation_date")
    if g.empty:
        return None
    end = g.iloc[-1]
    target = cutoff - pd.Timedelta(days=days)
    start_candidates = g[g["observation_date"] <= target]
    if start_candidates.empty:
        return None
    start = start_candidates.iloc[-1]
    if float(start["price"]) <= 0:
        return None
    return float(end["price"] / start["price"] - 1)


def trailing_volatility(group: pd.DataFrame, cutoff: pd.Timestamp) -> float | None:
    g = group[(group["knowledge_date"] <= cutoff) & (group["observation_date"] <= cutoff)].sort_values("observation_date").tail(13)
    if len(g) < 4:
        return None
    returns = g["price"].pct_change().dropna()
    if len(returns) < 3:
        return None
    return float(returns.std(ddof=1) * np.sqrt(12))


def decision_state(forecast_return: float | None, confidence: float | None, reconstructable: bool) -> str:
    if not reconstructable or forecast_return is None or confidence is None:
        return "INSUFFICIENT_EVIDENCE"
    if forecast_return >= 0.20 and confidence >= 50:
        return "FAVORABLE"
    if forecast_return >= 0.10 and confidence >= 40:
        return "WATCH"
    if forecast_return < -0.05:
        return "AVOID"
    return "NEUTRAL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    ledger = load_selected_ledger()
    eligibility = pd.read_csv(FOUNDATION / "collector_walk_forward_eligibility_matrix.csv", parse_dates=["decision_cutoff"])
    outcomes = pd.read_csv(FOUNDATION / "collector_walk_forward_outcome_availability.csv", parse_dates=["decision_cutoff"])

    pattern = cfg["collector_name_pattern"]
    eligibility = eligibility[eligibility["product_name"].str.contains(pattern, case=False, na=False)].copy()
    outcomes = outcomes[outcomes["product_name"].str.contains(pattern, case=False, na=False)].copy()
    collector_ledger = ledger[ledger["product_name"].str.contains(pattern, case=False, na=False)].copy()

    rows: list[dict[str, object]] = []
    for _, item in eligibility.iterrows():
        cutoff = pd.Timestamp(item["decision_cutoff"])
        key = str(item["product_key"])
        history_days = int(item["available_history_days"])
        group = collector_ledger[collector_ledger["product_key"].astype(str) == key]
        route = "INSUFFICIENT_HISTORY"
        reconstructable = False
        block_reason = ""
        forecast = None
        width = None
        downside = None
        upside = None
        confidence = None
        if history_days >= int(cfg["calibrated_history_days"]):
            route = "DIRECT_HISTORY_CALIBRATED_REPLAYABLE"
            forecast = trailing_return(group, cutoff, 365)
            vol = trailing_volatility(group, cutoff)
            if forecast is not None:
                reconstructable = True
                width = min(0.20, max(0.10, vol if vol is not None else 0.10))
                downside = max(-0.95, forecast - width)
                upside = forecast + width
                confidence = 70.0
            else:
                block_reason = "MISSING_365_DAY_ENTRY_PRICE"
        elif history_days >= int(cfg["minimum_history_days"]):
            route = "DIRECT_HISTORY_LIMITED_RECONSTRUCTION_REQUIRED"
            block_reason = "MISSING_POINT_IN_TIME_SIMILARITY_WEIGHTS_AND_FUNDAMENTAL_ADJUSTMENT"
            confidence = 5.0
        else:
            block_reason = "INSUFFICIENT_HISTORY"

        rows.append({
            "decision_cutoff": cutoff,
            "product_key": key,
            "product_name": item["product_name"],
            "entry_price": float(item["entry_price"]),
            "available_history_days": history_days,
            "historical_route": route,
            "forecast_reconstructable": reconstructable,
            "reconstruction_block_reason": block_reason,
            "forecast_return_365_equivalent": forecast,
            "scenario_width": width,
            "downside_annual_rate": downside,
            "upside_annual_rate": upside,
            "confidence_0_to_100": confidence,
            "test_only_decision_state": decision_state(forecast, confidence, reconstructable),
            "future_information_used": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
        })

    forecasts = pd.DataFrame(rows)
    scored = outcomes.merge(
        forecasts,
        on=["decision_cutoff", "product_key", "product_name", "entry_price"],
        how="inner",
    )
    scored = scored[scored["forecast_reconstructable"] == True].copy()
    if not scored.empty:
        scored["horizon_years"] = scored["horizon_days"] / 365.0
        scored["forecast_return_horizon"] = (1.0 + scored["forecast_return_365_equivalent"]) ** scored["horizon_years"] - 1.0
        scored["forecast_price"] = scored["entry_price"] * (1.0 + scored["forecast_return_horizon"])
        scored["signed_return_error"] = scored["forecast_return_horizon"] - scored["realized_return"]
        scored["absolute_return_error"] = scored["signed_return_error"].abs()
        scored["squared_return_error"] = scored["signed_return_error"] ** 2
        scored["no_change_absolute_error"] = scored["realized_return"].abs()
        scored["model_beats_no_change"] = scored["absolute_return_error"] < scored["no_change_absolute_error"]
        scored["direction_correct"] = np.sign(scored["forecast_return_horizon"]) == np.sign(scored["realized_return"])
        scored["inside_scenario"] = (
            scored["realized_return"] >= ((1 + scored["downside_annual_rate"]) ** scored["horizon_years"] - 1)
        ) & (
            scored["realized_return"] <= ((1 + scored["upside_annual_rate"]) ** scored["horizon_years"] - 1)
        )

    metric_rows: list[dict[str, object]] = []
    if not scored.empty:
        for horizon, g in scored.groupby("horizon_days"):
            metric_rows.append({
                "horizon_days": int(horizon),
                "forecast_count": int(len(g)),
                "product_count": int(g["product_key"].nunique()),
                "decision_cutoff_count": int(g["decision_cutoff"].nunique()),
                "mean_absolute_error": float(g["absolute_return_error"].mean()),
                "median_absolute_error": float(g["absolute_return_error"].median()),
                "root_mean_squared_error": float(np.sqrt(g["squared_return_error"].mean())),
                "mean_signed_error": float(g["signed_return_error"].mean()),
                "direction_accuracy": float(g["direction_correct"].mean()),
                "scenario_coverage": float(g["inside_scenario"].mean()),
                "model_beats_no_change_rate": float(g["model_beats_no_change"].mean()),
                "model_mean_absolute_error": float(g["absolute_return_error"].mean()),
                "no_change_mean_absolute_error": float(g["no_change_absolute_error"].mean()),
            })
    metrics = pd.DataFrame(metric_rows)

    route_summary = forecasts.groupby("historical_route", dropna=False).agg(
        product_cutoff_count=("product_key", "size"),
        unique_products=("product_key", "nunique"),
        decision_cutoffs=("decision_cutoff", "nunique"),
        reconstructable_count=("forecast_reconstructable", "sum"),
    ).reset_index()

    failures: list[str] = []
    if forecasts.empty:
        failures.append("no_collector_product_cutoffs")
    if not forecasts.empty and forecasts["future_information_used"].any():
        failures.append("future_information_used")
    if scored.empty:
        failures.append("no_reconstructable_scored_forecasts")

    forecasts.to_csv(OUT / "collector_walk_forward_phase_2a_forecasts.csv", index=False)
    scored.to_csv(OUT / "collector_walk_forward_phase_2a_scored_outcomes.csv", index=False)
    metrics.to_csv(OUT / "collector_walk_forward_phase_2a_accuracy_by_horizon.csv", index=False)
    route_summary.to_csv(OUT / "collector_walk_forward_phase_2a_route_reconstructability.csv", index=False)

    summary = {
        "audit_name": "Collector Walk-Forward Replay Phase 2A",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "collector_product_cutoff_count": int(len(forecasts)),
        "collector_product_count": int(forecasts["product_key"].nunique()) if not forecasts.empty else 0,
        "reconstructable_forecast_count": int(forecasts["forecast_reconstructable"].sum()) if not forecasts.empty else 0,
        "blocked_forecast_count": int((~forecasts["forecast_reconstructable"]).sum()) if not forecasts.empty else 0,
        "scored_outcome_count": int(len(scored)),
        "scored_90_day_count": int((scored["horizon_days"] == 90).sum()) if not scored.empty else 0,
        "scored_180_day_count": int((scored["horizon_days"] == 180).sum()) if not scored.empty else 0,
        "scored_365_day_count": int((scored["horizon_days"] == 365).sum()) if not scored.empty else 0,
        "full_v2_3_replay_complete": False,
        "comparable_and_limited_routes_blocked_without_point_in_time_inputs": True,
        "freeze_suspended_pending_walk_forward": True,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "Phase 2A scores only point-in-time calibrated-history forecasts that can be reconstructed from dated prices. Comparable and limited routes remain blocked until historical similarity weights and fundamental adjustments are reconstructable.",
    }
    (OUT / "collector_walk_forward_phase_2a_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
