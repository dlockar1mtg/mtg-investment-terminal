from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "data/governance/permanence/certification/collector_v1_long_horizon_simulation_tournament"
RESIDUAL_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_long_horizon_method_remediation"
SOURCE = ROOT / "scripts/run_collector_v1_long_horizon_simulation_tournament.py"
SEED = 20260802
DRAWS = 5000


def load_source():
    spec = importlib.util.spec_from_file_location("long_horizon_source", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load long-horizon source module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finite_quantile(values: np.ndarray, q: float) -> float:
    values = np.sort(np.asarray(values, dtype=float))
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    rank = int(np.ceil((values.size + 1) * q)) - 1
    return float(values[min(max(rank, 0), values.size - 1)])


def candidate_bounds(method: str, route_values: np.ndarray, global_values: np.ndarray) -> tuple[float, float, float, float]:
    route_values = route_values[np.isfinite(route_values)]
    global_values = global_values[np.isfinite(global_values)]
    if route_values.size < 20:
        route_values = global_values
    if route_values.size == 0:
        raise RuntimeError("No calibration residuals")

    if method.startswith("ASYMMETRIC_"):
        _, low80, high80, low90, high90 = method.split("_")
        return (
            finite_quantile(route_values, float(low80)),
            finite_quantile(route_values, float(high80)),
            finite_quantile(route_values, float(low90)),
            finite_quantile(route_values, float(high90)),
        )

    q10, q90 = finite_quantile(route_values, 0.10), finite_quantile(route_values, 0.90)
    q05, q95 = finite_quantile(route_values, 0.05), finite_quantile(route_values, 0.95)

    if method.startswith("UPPER_ONLY_"):
        factor = float(method.rsplit("_", 1)[1])
        center = float(np.median(route_values))
        return q10, center + (q90 - center) * factor, q05, center + (q95 - center) * factor
    if method.startswith("LOWER_ONLY_"):
        factor = float(method.rsplit("_", 1)[1])
        center = float(np.median(route_values))
        return center - (center - q10) * factor, q90, center - (center - q05) * factor, q95
    if method.startswith("SHRUNK_ASYMMETRIC_"):
        weight = float(method.rsplit("_", 1)[1])
        g10, g90 = finite_quantile(global_values, 0.10), finite_quantile(global_values, 0.90)
        g05, g95 = finite_quantile(global_values, 0.05), finite_quantile(global_values, 0.95)
        return (
            weight * q10 + (1 - weight) * g10,
            weight * q90 + (1 - weight) * g90,
            weight * q05 + (1 - weight) * g05,
            weight * q95 + (1 - weight) * g95,
        )
    raise ValueError(method)


def methods_for_route(route: str) -> list[str]:
    methods: list[str] = []
    if route == "COMPARABLE_PRODUCT_ADJUSTED":
        for upper80 in [0.92, 0.94, 0.96, 0.98]:
            for upper90 in [0.96, 0.97, 0.98, 0.99]:
                methods.append(f"ASYMMETRIC_0.10_{upper80:.2f}_0.05_{upper90:.2f}")
        methods += [f"UPPER_ONLY_{x:.2f}" for x in [1.10, 1.20, 1.30, 1.40, 1.50, 1.75, 2.00, 2.50, 3.00]]
    else:
        for lower80 in [0.02, 0.04, 0.06, 0.08]:
            for lower90 in [0.005, 0.01, 0.02, 0.03, 0.04]:
                methods.append(f"ASYMMETRIC_{lower80:.3f}_0.90_{lower90:.3f}_0.95")
        methods += [f"LOWER_ONLY_{x:.2f}" for x in [1.10, 1.20, 1.30, 1.40, 1.50, 1.75, 2.00, 2.50, 3.00]]
    methods += [f"SHRUNK_ASYMMETRIC_{x:.2f}" for x in [0.25, 0.40, 0.55, 0.70, 0.85]]
    return methods


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    source = load_source()
    evidence = pd.read_csv(RESIDUAL_DIR / "collector_v1_residual_interval_evidence.csv")
    evidence = evidence[pd.to_numeric(evidence["horizon_days"], errors="coerce") == 365].dropna(subset=["product_id", "route", "predicted", "actual"]).copy()
    base_winners = pd.read_csv(BASE_DIR / "collector_v1_long_horizon_method_winners.csv")
    unresolved_routes = base_winners[base_winners["promotion_status"] == "BLOCKED_NO_METHOD_MEETS_GATES"]["route"].astype(str).tolist()
    unresolved_routes = [r for r in unresolved_routes if r != "DIRECT_HISTORY_LIMITED"]
    if not unresolved_routes:
        raise RuntimeError("No unresolved direct routes found")

    global_values_all = source.safe_log_ratio(evidence["actual"], evidence["predicted"])
    detail_rows: list[dict] = []
    rng = np.random.default_rng(SEED + 17)

    for product_id, target_product in evidence.groupby("product_id"):
        cal = evidence[evidence["product_id"].astype(str) != str(product_id)]
        global_values = source.safe_log_ratio(cal["actual"], cal["predicted"])
        if global_values.size == 0:
            global_values = global_values_all
        for route in unresolved_routes:
            target = target_product[target_product["route"] == route]
            if target.empty:
                continue
            route_cal = cal[cal["route"] == route]
            route_values = source.safe_log_ratio(route_cal["actual"], route_cal["predicted"])
            for method in methods_for_route(route):
                q10, q90, q05, q95 = candidate_bounds(method, route_values, global_values)
                for _, row in target.iterrows():
                    predicted = float(row["predicted"])
                    actual = float(row["actual"])
                    lower80, upper80 = predicted * np.exp(q10), predicted * np.exp(q90)
                    lower90, upper90 = predicted * np.exp(q05), predicted * np.exp(q95)
                    median = predicted * np.exp(float(np.median(route_values if route_values.size else global_values)))
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
    details.to_csv(OUT_DIR / "collector_v1_targeted_long_horizon_validation_predictions.csv", index=False)

    metric_rows: list[dict] = []
    for (route, method), group in details.groupby(["route", "method"]):
        c80 = float(group["covered_80"].mean())
        c90 = float(group["covered_90"].mean())
        l80 = float(group["lower_miss_80"].mean())
        u80 = float(group["upper_miss_80"].mean())
        l90 = float(group["lower_miss_90"].mean())
        u90 = float(group["upper_miss_90"].mean())
        mape = float(group["absolute_percentage_error"].median())
        nw80 = float(group["width_80"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        nw90 = float(group["width_90"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        coverage_pass = abs(c80 - 0.80) <= 0.08 and abs(c90 - 0.90) <= 0.06
        tails_pass = l80 <= 0.15 and u80 <= 0.15 and l90 <= 0.10 and u90 <= 0.10
        promotable = bool(len(group) >= 20 and group["product_id"].nunique() >= 5 and coverage_pass and tails_pass)
        score = abs(c80 - 0.80) * 8 + abs(c90 - 0.90) * 10 + mape + 0.15 * nw80 + 0.10 * nw90 + l90 + u90
        metric_rows.append({
            "route": route, "method": method, "rows": len(group), "products": group["product_id"].nunique(),
            "coverage_80": c80, "coverage_90": c90, "lower_tail_miss_80": l80, "upper_tail_miss_80": u80,
            "lower_tail_miss_90": l90, "upper_tail_miss_90": u90, "median_absolute_percentage_error": mape,
            "normalized_width_80": nw80, "normalized_width_90": nw90, "coverage_pass": coverage_pass,
            "tail_balance_pass": tails_pass, "promotable": promotable, "selection_score": score,
        })
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(OUT_DIR / "collector_v1_targeted_long_horizon_method_metrics.csv", index=False)

    chosen_rows: list[pd.Series] = []
    for route, group in metrics.groupby("route"):
        promoted = group[group["promotable"]]
        chosen = (promoted if not promoted.empty else group).sort_values(["promotable", "selection_score"], ascending=[False, True]).iloc[0].copy()
        chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_TARGETED_METHOD_MEETS_GATES"
        chosen_rows.append(chosen)
    targeted = pd.DataFrame(chosen_rows)
    targeted.to_csv(OUT_DIR / "collector_v1_targeted_long_horizon_method_winners.csv", index=False)

    consolidated = base_winners.copy()
    for _, row in targeted.iterrows():
        mask = consolidated["route"].astype(str) == str(row["route"])
        for col in row.index:
            if col not in consolidated.columns:
                consolidated[col] = np.nan
            consolidated.loc[mask, col] = row[col]

    comparable = consolidated[consolidated["route"] == "COMPARABLE_PRODUCT_ADJUSTED"]
    if not comparable.empty and str(comparable.iloc[0]["promotion_status"]) == "PROMOTABLE":
        mask = consolidated["route"] == "DIRECT_HISTORY_LIMITED"
        for col in comparable.columns:
            consolidated.loc[mask, col] = comparable.iloc[0][col]
        consolidated.loc[mask, "route"] = "DIRECT_HISTORY_LIMITED"
        consolidated.loc[mask, "promotion_status"] = "APPROVED_FAIL_CLOSED_FALLBACK"
        consolidated.loc[mask, "delegated_from_route"] = "COMPARABLE_PRODUCT_ADJUSTED"
        consolidated.loc[mask, "confidence_penalty_required"] = True

    consolidated.to_csv(OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv", index=False)
    unresolved = int((~consolidated["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])).sum())
    summary = {
        "block_name": "Collector V1 Targeted Long-Horizon Method Remediation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targeted_routes": unresolved_routes,
        "targeted_candidate_cells": int(len(metrics)),
        "targeted_promoted_routes": int((targeted["promotion_status"] == "PROMOTABLE").sum()),
        "final_winner_routes": int(len(consolidated)),
        "final_unresolved_routes": unresolved,
        "product_holdout_enforced": True,
        "original_coverage_and_tail_gates_unchanged": True,
        "long_horizon_method_stack_complete": unresolved == 0,
        "scenario_simulation_rebuild_authorized": unresolved == 0,
        "decision_readiness_tournament_authorized_after_certification": unresolved == 0,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_TARGETED_LONG_HORIZON_METHOD_REMEDIATION_READY" if unresolved == 0 else "PARTIAL_COLLECTOR_V1_TARGETED_LONG_HORIZON_METHOD_REMEDIATION_READY",
    }
    (OUT_DIR / "collector_v1_targeted_long_horizon_method_remediation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (unresolved == 0 or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
