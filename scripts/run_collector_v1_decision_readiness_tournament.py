from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_long_horizon_scenario_authority"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_decision_readiness_tournament"

SCENARIO_ORDER = {
    "SCARCITY_UPSIDE": 4,
    "BASE": 3,
    "SUPPLY_EXPANSION": 2,
    "DEMAND_CONTRACTION": 1,
    "LIQUIDITY_SHOCK": 0,
}
REQUIRED_ROUTES = {
    "COMPARABLE_PRODUCT_ADJUSTED",
    "DIRECT_HISTORY_CALIBRATED",
    "DIRECT_HISTORY_LIMITED",
    "EARLY_OPPORTUNITY_COHORT_FALLBACK",
}
REQUIRED_HORIZONS = {1095, 1825}
REQUIRED_SCENARIOS = set(SCENARIO_ORDER)


def spearman(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 2:
        return 1.0
    return float(a.rank(method="average").corr(b.rank(method="average"), method="pearson"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    certification = json.loads(
        (SCENARIO_DIR / "collector_v1_final_long_horizon_scenario_authority_certification.json").read_text(encoding="utf-8")
    )
    if certification.get("decision_readiness_tournament_authorized") is not True:
        raise RuntimeError("Certified scenario authority does not authorize decision-readiness tournament")

    df = pd.read_csv(SCENARIO_DIR / "collector_v1_final_long_horizon_scenario_results.csv")
    numeric = [
        "horizon_days", "simulations", "p05_terminal_index", "p10_terminal_index",
        "median_terminal_index", "mean_terminal_index", "p90_terminal_index",
        "p95_terminal_index", "probability_of_loss", "probability_gain_25pct",
        "probability_gain_50pct",
    ]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["confidence_penalty_required"] = df["confidence_penalty_required"].astype(str).str.lower().eq("true")

    df["quantile_order_valid"] = (
        (df["p05_terminal_index"] <= df["p10_terminal_index"])
        & (df["p10_terminal_index"] <= df["median_terminal_index"])
        & (df["median_terminal_index"] <= df["p90_terminal_index"])
        & (df["p90_terminal_index"] <= df["p95_terminal_index"])
    )
    probability_cols = ["probability_of_loss", "probability_gain_25pct", "probability_gain_50pct"]
    df["probabilities_valid"] = df[probability_cols].ge(0).all(axis=1) & df[probability_cols].le(1).all(axis=1)
    df["scenario_rank"] = df["scenario"].map(SCENARIO_ORDER)

    # Conservative route-level utility used only for stability testing, not product recommendations.
    df["base_utility"] = (
        np.log(df["median_terminal_index"].clip(lower=1e-9))
        - 1.25 * df["probability_of_loss"]
        + 0.35 * df["probability_gain_25pct"]
        + 0.20 * df["probability_gain_50pct"]
    )
    df["confidence_multiplier"] = np.where(df["confidence_penalty_required"], 0.85, 1.0)
    df["penalized_utility"] = df["base_utility"] * df["confidence_multiplier"]

    # Maximum purchase-price multipliers relative to the current price index.
    # A value below 1.0 means the current price would need to fall to meet the specified downside-aware return target.
    df["max_price_multiplier_25pct_p10"] = df["p10_terminal_index"] / 1.25
    df["max_price_multiplier_50pct_p10"] = df["p10_terminal_index"] / 1.50
    df["max_price_multiplier_25pct_median"] = df["median_terminal_index"] / 1.25

    # Scenario monotonicity by route and horizon.
    monotonic_rows = []
    for (route, horizon), group in df.groupby(["route", "horizon_days"]):
        ordered = group.set_index("scenario")["median_terminal_index"].to_dict()
        complete = REQUIRED_SCENARIOS.issubset(ordered)
        monotonic = bool(
            complete
            and ordered["SCARCITY_UPSIDE"] >= ordered["BASE"]
            and ordered["BASE"] >= ordered["SUPPLY_EXPANSION"]
            and ordered["SUPPLY_EXPANSION"] >= ordered["DEMAND_CONTRACTION"]
            and ordered["DEMAND_CONTRACTION"] >= ordered["LIQUIDITY_SHOCK"]
        )
        monotonic_rows.append({"route": route, "horizon_days": int(horizon), "complete": complete, "scenario_monotonic": monotonic})
    monotonic_df = pd.DataFrame(monotonic_rows)

    # Rank stability across scenarios within each horizon.
    rank_rows = []
    for horizon, hgroup in df.groupby("horizon_days"):
        base = hgroup[hgroup["scenario"] == "BASE"].set_index("route")["penalized_utility"]
        for scenario, sgroup in hgroup.groupby("scenario"):
            current = sgroup.set_index("route")["penalized_utility"]
            common = sorted(set(base.index) & set(current.index))
            rho = spearman(base.loc[common], current.loc[common]) if common else float("nan")
            rank_rows.append({"horizon_days": int(horizon), "scenario": scenario, "rank_correlation_to_base": rho})
    rank_df = pd.DataFrame(rank_rows)

    # Purchase-price stability across scenarios for each route/horizon.
    stability_rows = []
    for (route, horizon), group in df.groupby(["route", "horizon_days"]):
        vals = group["max_price_multiplier_25pct_p10"].to_numpy(float)
        mean = float(np.mean(vals))
        cv = float(np.std(vals, ddof=0) / max(abs(mean), 1e-9))
        spread = float(np.max(vals) - np.min(vals))
        stability_rows.append({
            "route": route,
            "horizon_days": int(horizon),
            "purchase_price_multiplier_mean": mean,
            "purchase_price_multiplier_cv": cv,
            "purchase_price_multiplier_spread": spread,
            "confidence_penalty_required": bool(group["confidence_penalty_required"].any()),
        })
    stability_df = pd.DataFrame(stability_rows)

    # Delegation lineage must be explicit for limited history.
    limited = df[df["route"] == "DIRECT_HISTORY_LIMITED"]
    delegation_lineage_valid = bool(
        not limited.empty
        and limited["delegated_from_route"].astype(str).eq("COMPARABLE_PRODUCT_ADJUSTED").all()
        and limited["confidence_penalty_required"].all()
    )

    routes_complete = set(df["route"].astype(str)) == REQUIRED_ROUTES
    horizons_complete = set(df["horizon_days"].dropna().astype(int)) == REQUIRED_HORIZONS
    scenarios_complete = set(df["scenario"].astype(str)) == REQUIRED_SCENARIOS
    cells_complete = len(df) == 40 and not df.duplicated(["route", "horizon_days", "scenario"]).any()
    simulations_complete = bool((df["simulations"] == 10000).all())
    quantiles_valid = bool(df["quantile_order_valid"].all())
    probabilities_valid = bool(df["probabilities_valid"].all())
    scenario_monotonicity_pass = bool(monotonic_df["scenario_monotonic"].all())
    rank_correlations_finite = bool(np.isfinite(rank_df["rank_correlation_to_base"]).all())
    confidence_penalties_applied = bool((df.loc[df["confidence_penalty_required"], "confidence_multiplier"] < 1.0).all())
    purchase_price_metrics_finite = bool(np.isfinite(stability_df[["purchase_price_multiplier_cv", "purchase_price_multiplier_spread"]]).all().all())

    checks = {
        "routes_complete": routes_complete,
        "horizons_complete": horizons_complete,
        "scenarios_complete": scenarios_complete,
        "cells_complete": cells_complete,
        "simulations_complete": simulations_complete,
        "quantiles_valid": quantiles_valid,
        "probabilities_valid": probabilities_valid,
        "scenario_monotonicity_pass": scenario_monotonicity_pass,
        "rank_correlations_finite": rank_correlations_finite,
        "delegation_lineage_valid": delegation_lineage_valid,
        "confidence_penalties_applied": confidence_penalties_applied,
        "purchase_price_metrics_finite": purchase_price_metrics_finite,
    }
    critical_failures = [name for name, passed in checks.items() if not passed]
    framework_ready = not critical_failures

    df.to_csv(OUT_DIR / "collector_v1_decision_readiness_route_scenario_metrics.csv", index=False)
    monotonic_df.to_csv(OUT_DIR / "collector_v1_decision_readiness_scenario_monotonicity.csv", index=False)
    rank_df.to_csv(OUT_DIR / "collector_v1_decision_readiness_rank_stability.csv", index=False)
    stability_df.to_csv(OUT_DIR / "collector_v1_decision_readiness_purchase_price_stability.csv", index=False)

    summary = {
        "block_name": "Collector V1 Decision-Readiness Tournament",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_cells": int(len(df)),
        "routes": sorted(df["route"].astype(str).unique().tolist()),
        "horizons_days": sorted(df["horizon_days"].astype(int).unique().tolist()),
        "scenarios": sorted(df["scenario"].astype(str).unique().tolist()),
        "checks": checks,
        "critical_failures": critical_failures,
        "minimum_rank_correlation_to_base": float(rank_df["rank_correlation_to_base"].min()),
        "maximum_purchase_price_multiplier_cv": float(stability_df["purchase_price_multiplier_cv"].max()),
        "decision_framework_ready": framework_ready,
        "current_product_application_authorized_after_certification": framework_ready,
        "product_ranking_certified": False,
        "maximum_purchase_prices_certified": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Apply certified route stack to current governed products and run product-level ranking and purchase-price certification",
        "status": "PASS_COLLECTOR_V1_DECISION_READINESS_TOURNAMENT_READY" if framework_ready else "FAIL_COLLECTOR_V1_DECISION_READINESS_TOURNAMENT",
    }
    (OUT_DIR / "collector_v1_decision_readiness_tournament_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (framework_ready or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
