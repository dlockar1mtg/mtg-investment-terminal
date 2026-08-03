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
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_comparable_cluster_envelope_remediation"
ROUTE = "COMPARABLE_PRODUCT_ADJUSTED"


def finite_quantile(values: np.ndarray, q: float) -> float:
    values = np.sort(np.asarray(values, dtype=float))
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    rank = int(np.ceil((values.size + 1) * q)) - 1
    return float(values[min(max(rank, 0), values.size - 1)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    evidence = pd.read_csv(RESIDUAL_DIR / "collector_v1_residual_interval_evidence.csv")
    evidence = evidence[(pd.to_numeric(evidence["horizon_days"], errors="coerce") == 365) & (evidence["route"] == ROUTE)].copy()
    evidence = evidence.dropna(subset=["product_id", "predicted", "actual"])
    evidence["predicted"] = pd.to_numeric(evidence["predicted"], errors="coerce")
    evidence["actual"] = pd.to_numeric(evidence["actual"], errors="coerce")
    evidence = evidence[(evidence["predicted"] > 0) & (evidence["actual"] > 0)]
    evidence["log_residual"] = np.log(evidence["actual"] / evidence["predicted"])

    lower80_qs = [0.08, 0.10, 0.12]
    lower90_qs = [0.03, 0.05, 0.07]
    upper80_qs = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00]
    upper90_qs = [0.70, 0.80, 0.90, 0.95, 1.00]
    inflations = [1.00, 1.10, 1.25, 1.50, 2.00]

    detail_rows: list[dict] = []
    for product_id, target in evidence.groupby("product_id"):
        cal = evidence[evidence["product_id"].astype(str) != str(product_id)].copy()
        row_resid = cal["log_residual"].to_numpy(float)
        product_upper = cal.groupby("product_id")["log_residual"].max().clip(lower=0).to_numpy(float)
        for l80 in lower80_qs:
            low80 = finite_quantile(row_resid, l80)
            for l90 in lower90_qs:
                low90 = finite_quantile(row_resid, l90)
                for u80 in upper80_qs:
                    raw80 = finite_quantile(product_upper, u80)
                    for u90 in upper90_qs:
                        raw90 = finite_quantile(product_upper, u90)
                        for inflation in inflations:
                            high80 = raw80 * inflation
                            high90 = raw90 * inflation
                            method = f"CLUSTER_UPPER_L80_{l80:.2f}_L90_{l90:.2f}_U80_{u80:.2f}_U90_{u90:.2f}_X{inflation:.2f}"
                            for _, row in target.iterrows():
                                predicted = float(row["predicted"])
                                actual = float(row["actual"])
                                lower80 = predicted * np.exp(low80)
                                upper80 = predicted * np.exp(high80)
                                lower90 = predicted * np.exp(low90)
                                upper90 = predicted * np.exp(high90)
                                detail_rows.append({
                                    "product_id": product_id,
                                    "method": method,
                                    "predicted": predicted,
                                    "actual": actual,
                                    "covered_80": lower80 <= actual <= upper80,
                                    "covered_90": lower90 <= actual <= upper90,
                                    "lower_miss_80": actual < lower80,
                                    "upper_miss_80": actual > upper80,
                                    "lower_miss_90": actual < lower90,
                                    "upper_miss_90": actual > upper90,
                                    "width_80": upper80 - lower80,
                                    "width_90": upper90 - lower90,
                                    "median_absolute_percentage_error": abs(predicted - actual) / max(abs(actual), 1e-9),
                                    "product_holdout_enforced": True,
                                })

    details = pd.DataFrame(detail_rows)
    details.to_csv(OUT_DIR / "collector_v1_comparable_cluster_envelope_predictions.csv", index=False)

    metric_rows: list[dict] = []
    for method, group in details.groupby("method"):
        c80 = float(group["covered_80"].mean())
        c90 = float(group["covered_90"].mean())
        l80 = float(group["lower_miss_80"].mean())
        u80 = float(group["upper_miss_80"].mean())
        l90 = float(group["lower_miss_90"].mean())
        u90 = float(group["upper_miss_90"].mean())
        mape = float(group["median_absolute_percentage_error"].median())
        nw80 = float(group["width_80"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        nw90 = float(group["width_90"].mean()) / max(float(group["actual"].abs().median()), 1e-9)
        coverage_pass = abs(c80 - 0.80) <= 0.08 and abs(c90 - 0.90) <= 0.06
        tail_pass = l80 <= 0.15 and u80 <= 0.15 and l90 <= 0.10 and u90 <= 0.10
        promotable = bool(len(group) >= 20 and group["product_id"].nunique() >= 5 and coverage_pass and tail_pass)
        score = abs(c80 - 0.80) * 8 + abs(c90 - 0.90) * 10 + mape + 0.15 * nw80 + 0.10 * nw90 + l90 + u90
        metric_rows.append({
            "route": ROUTE,
            "method": method,
            "rows": len(group),
            "products": group["product_id"].nunique(),
            "coverage_80": c80,
            "coverage_90": c90,
            "lower_tail_miss_80": l80,
            "upper_tail_miss_80": u80,
            "lower_tail_miss_90": l90,
            "upper_tail_miss_90": u90,
            "median_absolute_percentage_error": mape,
            "normalized_width_80": nw80,
            "normalized_width_90": nw90,
            "coverage_pass": coverage_pass,
            "tail_balance_pass": tail_pass,
            "promotable": promotable,
            "selection_score": score,
        })

    metrics = pd.DataFrame(metric_rows).sort_values(["promotable", "selection_score"], ascending=[False, True])
    metrics.to_csv(OUT_DIR / "collector_v1_comparable_cluster_envelope_metrics.csv", index=False)
    promotable = metrics[metrics["promotable"]]
    chosen = (promotable if not promotable.empty else metrics).iloc[0].copy()
    chosen["promotion_status"] = "PROMOTABLE" if bool(chosen["promotable"]) else "BLOCKED_NO_CLUSTER_ENVELOPE_MEETS_GATES"
    pd.DataFrame([chosen]).to_csv(OUT_DIR / "collector_v1_comparable_cluster_envelope_winner.csv", index=False)

    base = pd.read_csv(TARGETED_DIR / "collector_v1_final_long_horizon_method_winners.csv")
    base = base[~base["route"].isin(["COMPARABLE_PRODUCT_ADJUSTED", "DIRECT_HISTORY_LIMITED"])].copy()
    comparable = chosen.copy()
    comparable["route"] = "COMPARABLE_PRODUCT_ADJUSTED"
    comparable["delegated_from_route"] = ""
    comparable["confidence_penalty_required"] = False
    limited = comparable.copy()
    limited["route"] = "DIRECT_HISTORY_LIMITED"
    limited["promotion_status"] = "APPROVED_FAIL_CLOSED_FALLBACK" if bool(chosen["promotable"]) else "BLOCKED_DEPENDENT_ON_COMPARABLE"
    limited["delegated_from_route"] = "COMPARABLE_PRODUCT_ADJUSTED"
    limited["confidence_penalty_required"] = True
    final = pd.concat([base, pd.DataFrame([comparable, limited])], ignore_index=True)
    final.to_csv(OUT_DIR / "collector_v1_final_long_horizon_method_winners.csv", index=False)

    unresolved = int((~final["promotion_status"].isin(["PROMOTABLE", "APPROVED_FAIL_CLOSED_FALLBACK"])).sum())
    summary = {
        "block_name": "Collector V1 Comparable Cluster Envelope Remediation",
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
        "final_winner_routes": int(len(final)),
        "final_unresolved_routes": unresolved,
        "product_holdout_enforced": True,
        "original_coverage_and_tail_gates_unchanged": True,
        "long_horizon_method_stack_complete": unresolved == 0,
        "scenario_simulation_rebuild_authorized": unresolved == 0,
        "decision_readiness_tournament_authorized_after_certification": unresolved == 0,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_COMPARABLE_CLUSTER_ENVELOPE_REMEDIATION_READY" if unresolved == 0 else "PARTIAL_COLLECTOR_V1_COMPARABLE_CLUSTER_ENVELOPE_REMEDIATION_READY",
    }
    (OUT_DIR / "collector_v1_comparable_cluster_envelope_remediation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (unresolved == 0 or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
