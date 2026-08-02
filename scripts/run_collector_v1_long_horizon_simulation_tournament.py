from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERVAL_DIR = ROOT / "data/governance/permanence/certification/collector_v1_lower_tail_interval_remediation"
RESIDUAL_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"
WINNER_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_short_horizon_winners"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_long_horizon_simulation_tournament"

METHODS = [
    "LOG_RETURN_BOOTSTRAP",
    "ROUTE_RESIDUAL_BOOTSTRAP",
    "STUDENT_T_RESIDUAL",
    "BLOCK_BOOTSTRAP",
    "REGIME_MIXTURE",
    "MEAN_REVERTING_DRIFT",
    "CONSERVATIVE_ENSEMBLE",
]
HORIZONS = [1095, 1825]
SCENARIOS = {
    "BASE": (0.00, 1.00),
    "SCARCITY_UPSIDE": (0.08, 1.00),
    "SUPPLY_EXPANSION": (-0.06, 1.05),
    "DEMAND_CONTRACTION": (-0.10, 1.10),
    "LIQUIDITY_SHOCK": (-0.15, 1.25),
}
SIMULATIONS = 10000
VALIDATION_DRAWS = 3000
SEED = 20260802


def safe_log_ratio(actual: pd.Series, predicted: pd.Series) -> np.ndarray:
    a = pd.to_numeric(actual, errors="coerce").to_numpy(float)
    p = pd.to_numeric(predicted, errors="coerce").to_numpy(float)
    mask = np.isfinite(a) & np.isfinite(p) & (a > 0) & (p > 0)
    return np.log(a[mask] / p[mask])


def finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values)]


def method_draws(method: str, route_values: np.ndarray, global_values: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    route_values = finite(route_values)
    global_values = finite(global_values)
    base = route_values if route_values.size >= 20 else global_values
    if base.size == 0:
        return np.zeros(n, dtype=float)

    if method == "LOG_RETURN_BOOTSTRAP":
        return rng.choice(global_values if global_values.size else base, size=n, replace=True)
    if method == "ROUTE_RESIDUAL_BOOTSTRAP":
        return rng.choice(base, size=n, replace=True)
    if method == "STUDENT_T_RESIDUAL":
        center = float(np.median(base))
        scale = float(np.std(base, ddof=1)) if base.size > 1 else 0.0
        scale = max(scale, 1e-6)
        return center + rng.standard_t(df=5, size=n) * scale * np.sqrt(3.0 / 5.0)
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
    if method == "REGIME_MIXTURE":
        q25, q75 = np.quantile(base, [0.25, 0.75])
        low = base[base <= q25]
        mid = base[(base > q25) & (base < q75)]
        high = base[base >= q75]
        regimes = rng.choice(3, size=n, p=[0.25, 0.50, 0.25])
        out = np.empty(n, dtype=float)
        pools = [low if low.size else base, mid if mid.size else base, high if high.size else base]
        for regime in range(3):
            mask = regimes == regime
            out[mask] = rng.choice(pools[regime], size=int(mask.sum()), replace=True)
        return out
    if method == "MEAN_REVERTING_DRIFT":
        draws = rng.choice(base, size=n, replace=True)
        return 0.55 * draws + 0.45 * float(np.median(base))
    if method == "CONSERVATIVE_ENSEMBLE":
        a = rng.choice(base, size=n, replace=True)
        center = float(np.median(base))
        scale = max(float(np.std(base, ddof=1)) if base.size > 1 else 0.0, 1e-6)
        b = center + rng.standard_t(df=5, size=n) * scale * np.sqrt(3.0 / 5.0)
        c = 0.55 * rng.choice(base, size=n, replace=True) + 0.45 * center
        stacked = np.vstack([a, b, c])
        return np.quantile(stacked, 0.40, axis=0)
    raise ValueError(method)


def validate_methods(evidence: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    global_values = safe_log_ratio(evidence["actual"], evidence["predicted"])
    detail_rows: list[dict] = []

    for product_id, target in evidence.groupby("product_id"):
        cal = evidence[evidence["product_id"].astype(str) != str(product_id)]
        global_cal = safe_log_ratio(cal["actual"], cal["predicted"])
        for route, route_target in target.groupby("route"):
            route_cal_frame = cal[cal["route"] == route]
            route_values = safe_log_ratio(route_cal_frame["actual"], route_cal_frame["predicted"])
            for method in METHODS:
                draws = method_draws(method, route_values, global_cal if global_cal.size else global_values, VALIDATION_DRAWS, rng)
                q05, q10, q50, q90, q95 = np.quantile(draws, [0.05, 0.10, 0.50, 0.90, 0.95])
                for _, row in route_target.iterrows():
                    predicted = float(row["predicted"])
                    actual = float(row["actual"])
                    lower80, upper80 = predicted * np.exp(q10), predicted * np.exp(q90)
                    lower90, upper90 = predicted * np.exp(q05), predicted * np.exp(q95)
                    median = predicted * np.exp(q50)
                    detail_rows.append({
                        "product_id": product_id,
                        "route": route,
                        "method": method,
                        "predicted": predicted,
                        "actual": actual,
                        "median_simulated": median,
                        "covered_80": lower80 <= actual <= upper80,
                        "covered_90": lower90 <= actual <= upper90,
                        "lower_miss_80": actual < lower80,
                        "upper_miss_80": actual > upper80,
                        "lower_miss_90": actual < lower90,
                        "upper_miss_90": actual > upper90,
                        "width_80": upper80 - lower80,
                        "width_90": upper90 - lower90,
                        "absolute_percentage_error": abs(median - actual) / max(abs(actual), 1e-9),
                        "product_holdout_enforced": True,
                    })

    details = pd.DataFrame(detail_rows)
    metric_rows: list[dict] = []
    for (route, method), group in details.groupby(["route", "method"]):
        coverage80 = float(group["covered_80"].mean())
        coverage90 = float(group["covered_90"].mean())
        lower80 = float(group["lower_miss_80"].mean())
        upper80 = float(group["upper_miss_80"].mean())
        lower90 = float(group["lower_miss_90"].mean())
        upper90 = float(group["upper_miss_90"].mean())
        mape = float(group["absolute_percentage_error"].median())
        normalized_width80 = float(group["width_80"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        normalized_width90 = float(group["width_90"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        coverage_pass = abs(coverage80 - 0.80) <= 0.08 and abs(coverage90 - 0.90) <= 0.06
        tails_pass = lower80 <= 0.15 and upper80 <= 0.15 and lower90 <= 0.10 and upper90 <= 0.10
        promotable = bool(len(group) >= 20 and group["product_id"].nunique() >= 5 and coverage_pass and tails_pass)
        score = abs(coverage80 - 0.80) * 8 + abs(coverage90 - 0.90) * 10 + mape + 0.15 * normalized_width80 + 0.10 * normalized_width90 + lower90 + upper90
        metric_rows.append({
            "route": route,
            "method": method,
            "rows": len(group),
            "products": group["product_id"].nunique(),
            "coverage_80": coverage80,
            "coverage_90": coverage90,
            "lower_tail_miss_80": lower80,
            "upper_tail_miss_80": upper80,
            "lower_tail_miss_90": lower90,
            "upper_tail_miss_90": upper90,
            "median_absolute_percentage_error": mape,
            "normalized_width_80": normalized_width80,
            "normalized_width_90": normalized_width90,
            "coverage_pass": coverage_pass,
            "tail_balance_pass": tails_pass,
            "promotable": promotable,
            "selection_score": score,
        })

    metrics = pd.DataFrame(metric_rows)
    winners: list[pd.Series] = []
    for _, group in metrics.groupby("route"):
        promotable = group[group["promotable"]]
        chosen = (promotable if not promotable.empty else group).sort_values(["promotable", "selection_score"], ascending=[False, True]).iloc[0].copy()
        chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_METHOD_MEETS_GATES"
        winners.append(chosen)
    return details, pd.DataFrame(winners)


def simulate_long_horizon(evidence: pd.DataFrame, winners: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 1)
    global_values = safe_log_ratio(evidence["actual"], evidence["predicted"])
    rows: list[dict] = []
    for _, winner in winners.iterrows():
        route = str(winner["route"])
        method = str(winner["method"])
        route_frame = evidence[evidence["route"] == route]
        route_values = safe_log_ratio(route_frame["actual"], route_frame["predicted"])
        if route_values.size < 20:
            route_values = global_values
        for horizon in HORIZONS:
            years = horizon // 365
            for scenario, (drift_shift, vol_multiplier) in SCENARIOS.items():
                annual = method_draws(method, route_values, global_values, SIMULATIONS * years, rng).reshape(SIMULATIONS, years)
                annual = annual * vol_multiplier + drift_shift
                terminal = np.exp(annual.sum(axis=1))
                rows.append({
                    "route": route,
                    "method": method,
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
                    "deterministic_seed": SEED + 1,
                })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    interval_cert = json.loads((INTERVAL_DIR / "collector_v1_lower_tail_interval_remediation_certification.json").read_text(encoding="utf-8"))
    if interval_cert.get("long_horizon_simulation_tournament_authorized") is not True:
        raise RuntimeError("Certified residual/interval stack does not authorize long-horizon tournament")

    evidence = pd.read_csv(RESIDUAL_DIR / "collector_v1_residual_interval_evidence.csv")
    evidence = evidence[(pd.to_numeric(evidence["horizon_days"], errors="coerce") == 365)].copy()
    evidence = evidence.dropna(subset=["product_id", "route", "predicted", "actual"])
    manifest = pd.read_csv(WINNER_DIR / "collector_v1_final_short_horizon_winner_manifest.csv")

    details, winners = validate_methods(evidence)
    details.to_csv(OUT_DIR / "collector_v1_long_horizon_validation_predictions.csv", index=False)

    metric_rows: list[pd.DataFrame] = []
    for route, group in details.groupby("route"):
        metrics = []
        for method, m in group.groupby("method"):
            row = winners[(winners["route"] == route) & (winners["method"] == method)]
            metrics.append(row.iloc[0].to_dict() if not row.empty else {})
        metric_rows.append(pd.DataFrame(metrics))
    winner_routes = winners.copy()

    available_routes = set(winner_routes["route"].astype(str))
    manifest_routes = set(manifest["resolved_route"].dropna().astype(str))
    if "DIRECT_HISTORY_LIMITED" in manifest_routes and "DIRECT_HISTORY_LIMITED" not in available_routes:
        delegate = winner_routes[winner_routes["route"] == "COMPARABLE_PRODUCT_ADJUSTED"]
        if not delegate.empty:
            delegated = delegate.iloc[0].copy()
            delegated["route"] = "DIRECT_HISTORY_LIMITED"
            delegated["promotion_status"] = "APPROVED_FAIL_CLOSED_FALLBACK"
            delegated["delegated_from_route"] = "COMPARABLE_PRODUCT_ADJUSTED"
            delegated["confidence_penalty_required"] = True
            winner_routes = pd.concat([winner_routes, pd.DataFrame([delegated])], ignore_index=True)

    winner_routes.to_csv(OUT_DIR / "collector_v1_long_horizon_method_winners.csv", index=False)
    simulations = simulate_long_horizon(evidence, winner_routes[winner_routes["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])])
    simulations.to_csv(OUT_DIR / "collector_v1_long_horizon_scenario_results.csv", index=False)

    unresolved = int((~winner_routes["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])).sum())
    expected_simulation_cells = int(len(winner_routes[winner_routes["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])]) * len(HORIZONS) * len(SCENARIOS))
    summary = {
        "block_name": "Collector V1 Long-Horizon Simulation Tournament",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "historical_validation_rows": int(len(evidence)),
        "historical_products": int(evidence["product_id"].nunique()),
        "methods_tested": METHODS,
        "validated_routes": sorted(evidence["route"].astype(str).unique().tolist()),
        "winner_routes": int(len(winner_routes)),
        "unresolved_winner_routes": unresolved,
        "horizons_days": HORIZONS,
        "scenarios": list(SCENARIOS),
        "simulations_per_route_horizon_scenario": SIMULATIONS,
        "simulation_result_cells": int(len(simulations)),
        "expected_simulation_result_cells": expected_simulation_cells,
        "product_holdout_enforced": True,
        "deterministic_seed": SEED,
        "direct_three_five_year_backtest_claimed": False,
        "long_horizon_simulation_tournament_ready": unresolved == 0 and len(simulations) == expected_simulation_cells,
        "decision_readiness_tournament_authorized_after_certification": unresolved == 0 and len(simulations) == expected_simulation_cells,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_LONG_HORIZON_SIMULATION_TOURNAMENT_READY" if unresolved == 0 and len(simulations) == expected_simulation_cells else "PARTIAL_COLLECTOR_V1_LONG_HORIZON_SIMULATION_TOURNAMENT_READY",
    }
    (OUT_DIR / "collector_v1_long_horizon_simulation_tournament_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (summary["long_horizon_simulation_tournament_ready"] or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
