from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESIDUAL_DIR = ROOT / "data/governance/permanence/certification/collector_v1_residual_interval_tournament"
TARGETED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_long_horizon_method_remediation"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_comparable_location_tail_remediation"
ROUTE = "COMPARABLE_PRODUCT_ADJUSTED"


def finite_quantile(values: np.ndarray, q: float) -> float:
    values = np.asarray(values, dtype=float)
    values = np.sort(values[np.isfinite(values)])
    if values.size == 0:
        return float("nan")
    rank = int(np.ceil((values.size + 1) * q)) - 1
    return float(values[min(max(rank, 0), values.size - 1)])


def log_ratios(frame: pd.DataFrame) -> np.ndarray:
    actual = pd.to_numeric(frame["actual"], errors="coerce").to_numpy(float)
    predicted = pd.to_numeric(frame["predicted"], errors="coerce").to_numpy(float)
    mask = np.isfinite(actual) & np.isfinite(predicted) & (actual > 0) & (predicted > 0)
    return np.log(actual[mask] / predicted[mask])


def product_balanced_residuals(frame: pd.DataFrame, aggregation: str) -> np.ndarray:
    rows: list[float] = []
    for _, group in frame.groupby("product_id"):
        values = log_ratios(group)
        if values.size == 0:
            continue
        if aggregation == "MEDIAN":
            rows.append(float(np.median(values)))
        elif aggregation == "P90":
            rows.append(finite_quantile(values, 0.90))
        elif aggregation == "MAX":
            rows.append(float(np.max(values)))
        else:
            raise ValueError(aggregation)
    return np.asarray(rows, dtype=float)


def candidate_specs() -> list[dict]:
    specs: list[dict] = []
    for source in ["ROW_WEIGHTED", "PRODUCT_MEDIAN", "PRODUCT_P90", "PRODUCT_MAX"]:
        for upper80 in [0.94, 0.96, 0.98, 0.99, 0.995, 1.00]:
            for upper90 in [0.97, 0.98, 0.99, 0.995, 1.00]:
                specs.append({
                    "method": f"{source}_FINITE_UPPER_{upper80:.3f}_{upper90:.3f}",
                    "source": source,
                    "lower80": 0.10,
                    "upper80": upper80,
                    "lower90": 0.05,
                    "upper90": upper90,
                    "center": 0.50,
                })
    for center in [0.55, 0.60, 0.65, 0.70]:
        for upper80, upper90 in [(0.98, 0.99), (0.99, 0.995), (0.995, 1.00)]:
            specs.append({
                "method": f"ROW_WEIGHTED_RECENTER_{center:.2f}_UPPER_{upper80:.3f}_{upper90:.3f}",
                "source": "ROW_WEIGHTED",
                "lower80": 0.10,
                "upper80": upper80,
                "lower90": 0.05,
                "upper90": upper90,
                "center": center,
            })
    return specs


def source_values(cal: pd.DataFrame, source: str) -> np.ndarray:
    if source == "ROW_WEIGHTED":
        return log_ratios(cal)
    if source == "PRODUCT_MEDIAN":
        return product_balanced_residuals(cal, "MEDIAN")
    if source == "PRODUCT_P90":
        return product_balanced_residuals(cal, "P90")
    if source == "PRODUCT_MAX":
        return product_balanced_residuals(cal, "MAX")
    raise ValueError(source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targeted_summary = json.loads((TARGETED_DIR / "collector_v1_targeted_long_horizon_method_remediation_summary.json").read_text(encoding="utf-8"))
    if int(targeted_summary.get("final_unresolved_routes", -1)) != 1:
        raise RuntimeError("Expected exactly one unresolved long-horizon route before comparable remediation")

    evidence = pd.read_csv(RESIDUAL_DIR / "collector_v1_residual_interval_evidence.csv")
    evidence = evidence[(evidence["route"].astype(str) == ROUTE) & (pd.to_numeric(evidence["horizon_days"], errors="coerce") == 365)].copy()
    evidence = evidence.dropna(subset=["product_id", "predicted", "actual"])
    if evidence.empty:
        raise RuntimeError("Comparable route has no 365-day historical evidence")

    specs = candidate_specs()
    detail_rows: list[dict] = []
    for product_id, target in evidence.groupby("product_id"):
        cal = evidence[evidence["product_id"].astype(str) != str(product_id)]
        for spec in specs:
            values = source_values(cal, spec["source"])
            if values.size < 5:
                continue
            q10 = finite_quantile(values, spec["lower80"])
            q90 = finite_quantile(values, spec["upper80"])
            q05 = finite_quantile(values, spec["lower90"])
            q95 = finite_quantile(values, spec["upper90"])
            center = finite_quantile(values, spec["center"])
            for _, row in target.iterrows():
                predicted = float(row["predicted"])
                actual = float(row["actual"])
                lower80, upper80 = predicted * np.exp(q10), predicted * np.exp(q90)
                lower90, upper90 = predicted * np.exp(q05), predicted * np.exp(q95)
                median = predicted * np.exp(center)
                detail_rows.append({
                    "product_id": product_id,
                    "route": ROUTE,
                    "method": spec["method"],
                    "source": spec["source"],
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
                    "calibration_products": int(cal["product_id"].nunique()),
                    "product_holdout_enforced": True,
                })

    details = pd.DataFrame(detail_rows)
    details.to_csv(OUT_DIR / "collector_v1_comparable_location_tail_predictions.csv", index=False)

    metric_rows: list[dict] = []
    for method, group in details.groupby("method"):
        coverage80 = float(group["covered_80"].mean())
        coverage90 = float(group["covered_90"].mean())
        lower80 = float(group["lower_miss_80"].mean())
        upper80 = float(group["upper_miss_80"].mean())
        lower90 = float(group["lower_miss_90"].mean())
        upper90 = float(group["upper_miss_90"].mean())
        mape = float(group["absolute_percentage_error"].median())
        width80 = float(group["width_80"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        width90 = float(group["width_90"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        coverage_pass = abs(coverage80 - 0.80) <= 0.08 and abs(coverage90 - 0.90) <= 0.06
        tails_pass = lower80 <= 0.15 and upper80 <= 0.15 and lower90 <= 0.10 and upper90 <= 0.10
        promotable = bool(len(group) >= 20 and group["product_id"].nunique() >= 5 and coverage_pass and tails_pass)
        score = abs(coverage80 - 0.80) * 8 + abs(coverage90 - 0.90) * 10 + mape + 0.15 * width80 + 0.10 * width90 + lower90 + upper90
        metric_rows.append({
            "route": ROUTE,
            "method": method,
            "rows": len(group),
            "products": int(group["product_id"].nunique()),
            "coverage_80": coverage80,
            "coverage_90": coverage90,
            "lower_tail_miss_80": lower80,
            "upper_tail_miss_80": upper80,
            "lower_tail_miss_90": lower90,
            "upper_tail_miss_90": upper90,
            "median_absolute_percentage_error": mape,
            "normalized_width_80": width80,
            "normalized_width_90": width90,
            "coverage_pass": coverage_pass,
            "tail_balance_pass": tails_pass,
            "promotable": promotable,
            "selection_score": score,
        })

    metrics = pd.DataFrame(metric_rows).sort_values(["promotable", "selection_score"], ascending=[False, True])
    metrics.to_csv(OUT_DIR / "collector_v1_comparable_location_tail_metrics.csv", index=False)
    promotable = metrics[metrics["promotable"]]
    chosen = (promotable if not promotable.empty else metrics).iloc[0].copy()
    chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_LOCATION_TAIL_METHOD_MEETS_GATES"
    pd.DataFrame([chosen]).to_csv(OUT_DIR / "collector_v1_comparable_location_tail_winner.csv", index=False)

    previous = pd.read_csv(TARGETED_DIR / "collector_v1_final_long_horizon_method_winners.csv")
    comparable_mask = previous["route"].astype(str) == ROUTE
    for col in chosen.index:
        if col not in previous.columns:
            previous[col] = np.nan
        previous.loc[comparable_mask, col] = chosen[col]
    limited_mask = previous["route"].astype(str) == "DIRECT_HISTORY_LIMITED"
    if bool(chosen["promotable"]):
        for col in chosen.index:
            previous.loc[limited_mask, col] = chosen[col]
        previous.loc[limited_mask, "route"] = "DIRECT_HISTORY_LIMITED"
        previous.loc[limited_mask, "promotion_status"] = "APPROVED_FAIL_CLOSED_FALLBACK"
        previous.loc[limited_mask, "delegated_from_route"] = ROUTE
        previous.loc[limited_mask, "confidence_penalty_required"] = True
    previous.to_csv(OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv", index=False)

    unresolved = int((~previous["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])).sum())
    summary = {
        "block_name": "Collector V1 Comparable Location and Upper-Tail Remediation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "historical_rows": int(len(evidence)),
        "historical_products": int(evidence["product_id"].nunique()),
        "candidate_methods": int(len(metrics)),
        "selected_method": str(chosen["method"]),
        "selected_coverage_80": float(chosen["coverage_80"]),
        "selected_coverage_90": float(chosen["coverage_90"]),
        "selected_lower_tail_miss_80": float(chosen["lower_tail_miss_80"]),
        "selected_upper_tail_miss_80": float(chosen["upper_tail_miss_80"]),
        "selected_lower_tail_miss_90": float(chosen["lower_tail_miss_90"]),
        "selected_upper_tail_miss_90": float(chosen["upper_tail_miss_90"]),
        "comparable_route_resolved": bool(chosen["promotable"]),
        "final_winner_routes": int(len(previous)),
        "final_unresolved_routes": unresolved,
        "product_holdout_enforced": True,
        "original_coverage_and_tail_gates_unchanged": True,
        "long_horizon_method_stack_complete": unresolved == 0,
        "scenario_simulation_rebuild_authorized": unresolved == 0,
        "decision_readiness_tournament_authorized_after_certification": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_COMPARABLE_LOCATION_TAIL_REMEDIATION_READY" if unresolved == 0 else "PARTIAL_COLLECTOR_V1_COMPARABLE_LOCATION_TAIL_REMEDIATION_READY",
    }
    (OUT_DIR / "collector_v1_comparable_location_tail_remediation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (unresolved == 0 or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
