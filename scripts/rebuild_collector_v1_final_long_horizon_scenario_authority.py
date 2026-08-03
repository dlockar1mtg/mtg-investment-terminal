from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
METHOD_DIR = ROOT / "data/governance/permanence/certification/collector_v1_comparable_cluster_envelope_remediation"
RESIDUAL_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_long_horizon_scenario_authority"

HORIZONS = [1095, 1825]
SCENARIOS = {
    "BASE": (0.00, 1.00),
    "SCARCITY_UPSIDE": (0.08, 1.00),
    "SUPPLY_EXPANSION": (-0.06, 1.05),
    "DEMAND_CONTRACTION": (-0.10, 1.10),
    "LIQUIDITY_SHOCK": (-0.15, 1.25),
}
SIMULATIONS = 10000
SEED = 20260802


def finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values)]


def safe_log_ratio(frame: pd.DataFrame) -> np.ndarray:
    actual = pd.to_numeric(frame["actual"], errors="coerce").to_numpy(float)
    predicted = pd.to_numeric(frame["predicted"], errors="coerce").to_numpy(float)
    mask = np.isfinite(actual) & np.isfinite(predicted) & (actual > 0) & (predicted > 0)
    return np.log(actual[mask] / predicted[mask])


def parse_cluster_method(method: str) -> tuple[float, float, float, float, float]:
    parts = method.split("_")
    values: dict[str, float] = {}
    for i, part in enumerate(parts):
        if part in {"L80", "L90", "U80", "U90"} and i + 1 < len(parts):
            values[part] = float(parts[i + 1])
        if part.startswith("X") and len(part) > 1:
            values["X"] = float(part[1:])
    return values.get("L80", 0.08), values.get("L90", 0.03), values.get("U80", 0.50), values.get("U90", 0.70), values.get("X", 1.00)


def annual_draws(method: str, route_frame: pd.DataFrame, global_values: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    route_values = safe_log_ratio(route_frame)
    base = route_values if route_values.size >= 20 else global_values
    if base.size == 0:
        return np.zeros(n, dtype=float)

    if method == "BLOCK_BOOTSTRAP":
        block = max(2, min(6, int(np.sqrt(base.size))))
        out = np.empty(n, dtype=float)
        for i in range(0, n, block):
            start = int(rng.integers(0, max(1, base.size - block + 1)))
            chunk = base[start:start + block]
            if chunk.size < block:
                chunk = np.resize(chunk, block)
            out[i:i + block] = chunk[: min(block, n - i)]
        return out

    if method.startswith("LOWER_ONLY_"):
        factor = float(method.rsplit("_", 1)[1])
        draws = rng.choice(base, size=n, replace=True)
        center = float(np.median(base))
        return np.where(draws < center, center + (draws - center) * factor, draws)

    if method.startswith("CLUSTER_UPPER_"):
        _, _, upper80_q, upper90_q, inflation = parse_cluster_method(method)
        draws = rng.choice(base, size=n, replace=True)
        product_maxima = []
        for _, product in route_frame.groupby("product_id"):
            vals = safe_log_ratio(product)
            positive = vals[vals > 0]
            if positive.size:
                product_maxima.append(float(np.max(positive)))
        maxima = finite(np.asarray(product_maxima, dtype=float))
        if maxima.size:
            envelope_q = max(upper80_q, upper90_q)
            upper_cap = float(np.quantile(maxima, envelope_q)) * inflation
            center = float(np.median(base))
            positive_mask = draws > center
            draws[positive_mask] = np.maximum(draws[positive_mask], rng.uniform(center, max(center, upper_cap), positive_mask.sum()))
        return draws

    return rng.choice(base, size=n, replace=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cert = json.loads((METHOD_DIR / "collector_v1_comparable_cluster_envelope_remediation_certification.json").read_text(encoding="utf-8"))
    if cert.get("scenario_simulation_rebuild_authorized") is not True:
        raise RuntimeError("Certified method stack does not authorize scenario rebuild")

    winners = pd.read_csv(METHOD_DIR / "collector_v1_final_long_horizon_method_winners.csv")
    evidence = pd.read_csv(RESIDUAL_DIR / "collector_v1_residual_interval_evidence.csv")
    evidence = evidence[pd.to_numeric(evidence["horizon_days"], errors="coerce") == 365].copy()
    evidence = evidence.dropna(subset=["product_id", "route", "predicted", "actual"])
    global_values = safe_log_ratio(evidence)

    expected_routes = {
        "COMPARABLE_PRODUCT_ADJUSTED",
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "EARLY_OPPORTUNITY_COHORT_FALLBACK",
    }
    available_routes = set(winners["route"].astype(str))
    missing_routes = sorted(expected_routes - available_routes)
    unresolved = winners[~winners["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])]

    rng = np.random.default_rng(SEED)
    rows: list[dict] = []
    for _, winner in winners.iterrows():
        route = str(winner["route"])
        method = str(winner["method"])
        delegated_from = str(winner.get("delegated_from_route", "") or "")
        source_route = delegated_from if delegated_from and delegated_from != "nan" else route
        route_frame = evidence[evidence["route"].astype(str) == source_route].copy()
        if route_frame.empty and route == "DIRECT_HISTORY_LIMITED":
            route_frame = evidence[evidence["route"].astype(str) == "COMPARABLE_PRODUCT_ADJUSTED"].copy()
        for horizon in HORIZONS:
            years = horizon // 365
            for scenario, (drift_shift, vol_multiplier) in SCENARIOS.items():
                annual = annual_draws(method, route_frame, global_values, SIMULATIONS * years, rng).reshape(SIMULATIONS, years)
                annual = annual * vol_multiplier + drift_shift
                terminal = np.exp(annual.sum(axis=1))
                rows.append({
                    "route": route,
                    "method": method,
                    "delegated_from_route": delegated_from,
                    "confidence_penalty_required": bool(winner.get("confidence_penalty_required", False)),
                    "horizon_days": horizon,
                    "years": years,
                    "scenario": scenario,
                    "simulations": SIMULATIONS,
                    "starting_value_index": 1.0,
                    "p05_terminal_index": float(np.quantile(terminal, 0.05)),
                    "p10_terminal_index": float(np.quantile(terminal, 0.10)),
                    "p25_terminal_index": float(np.quantile(terminal, 0.25)),
                    "median_terminal_index": float(np.quantile(terminal, 0.50)),
                    "mean_terminal_index": float(np.mean(terminal)),
                    "p75_terminal_index": float(np.quantile(terminal, 0.75)),
                    "p90_terminal_index": float(np.quantile(terminal, 0.90)),
                    "p95_terminal_index": float(np.quantile(terminal, 0.95)),
                    "probability_of_loss": float(np.mean(terminal < 1.0)),
                    "probability_gain_25pct": float(np.mean(terminal >= 1.25)),
                    "probability_gain_50pct": float(np.mean(terminal >= 1.50)),
                    "deterministic_seed": SEED,
                })

    results = pd.DataFrame(rows)
    results.to_csv(OUT_DIR / "collector_v1_final_long_horizon_scenario_results.csv", index=False)
    winners.to_csv(OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv", index=False)

    expected_cells = len(expected_routes) * len(HORIZONS) * len(SCENARIOS)
    complete = not missing_routes and unresolved.empty and len(results) == expected_cells and (results["simulations"] == SIMULATIONS).all()
    summary = {
        "block_name": "Collector V1 Final Long-Horizon Scenario Authority Rebuild",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method_routes": int(len(winners)),
        "missing_routes": missing_routes,
        "unresolved_method_routes": int(len(unresolved)),
        "horizons_days": HORIZONS,
        "scenarios": list(SCENARIOS),
        "simulations_per_route_horizon_scenario": SIMULATIONS,
        "scenario_result_cells": int(len(results)),
        "expected_scenario_result_cells": expected_cells,
        "total_simulation_draws": int(len(results) * SIMULATIONS),
        "deterministic_seed": SEED,
        "direct_three_five_year_backtest_claimed": False,
        "final_scenario_authority_complete": bool(complete),
        "decision_readiness_tournament_authorized_after_certification": bool(complete),
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_FINAL_LONG_HORIZON_SCENARIO_AUTHORITY_READY" if complete else "FAIL_COLLECTOR_V1_FINAL_LONG_HORIZON_SCENARIO_AUTHORITY",
    }
    (OUT_DIR / "collector_v1_final_long_horizon_scenario_authority_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (complete or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
