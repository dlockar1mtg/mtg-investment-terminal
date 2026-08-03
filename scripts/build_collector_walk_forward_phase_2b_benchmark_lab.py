from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2b_benchmark_lab_v1.json"
SOURCE = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2b_benchmark_lab/candidate_v1_0_0"


def annual_to_horizon(rate: pd.Series, years: pd.Series) -> pd.Series:
    return np.power(1.0 + rate, years) - 1.0


def build_variant_rates(scored: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    base = pd.to_numeric(scored["forecast_return_365_equivalent"], errors="coerce")
    years = pd.to_numeric(scored["horizon_days"], errors="coerce") / 365.0
    cutoff_medians = scored.assign(_base=base).groupby(["decision_cutoff", "horizon_days"])["_base"].transform("median")
    rows: list[pd.DataFrame] = []
    for name, spec in cfg["forecast_variants"].items():
        kind = spec["kind"]
        if kind == "constant":
            annual = pd.Series(float(spec["value"]), index=scored.index)
        elif kind == "scale":
            annual = base * float(spec["scale"])
        elif kind == "cap_annual":
            annual = base.clip(float(spec["lower"]), float(spec["upper"]))
        elif kind == "median_blend":
            w = float(spec["model_weight"])
            annual = w * base + (1.0 - w) * cutoff_medians
        else:
            raise ValueError(f"Unsupported variant kind: {kind}")
        part = scored[["decision_cutoff", "product_key", "product_name", "horizon_days", "realized_return", "entry_price", "test_only_decision_state"]].copy()
        part["variant_name"] = name
        part["variant_annual_rate"] = annual
        part["variant_forecast_return"] = annual_to_horizon(annual, years)
        part["signed_error"] = part["variant_forecast_return"] - pd.to_numeric(part["realized_return"], errors="coerce")
        part["absolute_error"] = part["signed_error"].abs()
        part["squared_error"] = part["signed_error"] ** 2
        part["direction_correct"] = np.sign(part["variant_forecast_return"]) == np.sign(pd.to_numeric(part["realized_return"], errors="coerce"))
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def summarize_variants(rows: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for (horizon, variant), g in rows.groupby(["horizon_days", "variant_name"]):
        records.append({
            "horizon_days": int(horizon),
            "variant_name": variant,
            "case_count": int(len(g)),
            "product_count": int(g["product_key"].nunique()),
            "decision_cutoff_count": int(g["decision_cutoff"].nunique()),
            "mean_absolute_error": float(g["absolute_error"].mean()),
            "median_absolute_error": float(g["absolute_error"].median()),
            "root_mean_squared_error": float(np.sqrt(g["squared_error"].mean())),
            "mean_signed_error": float(g["signed_error"].mean()),
            "direction_accuracy": float(g["direction_correct"].mean()),
        })
    out = pd.DataFrame(records)
    out["mae_rank_within_horizon"] = out.groupby("horizon_days")["mean_absolute_error"].rank(method="dense")
    return out.sort_values(["horizon_days", "mae_rank_within_horizon", "variant_name"])


def scenario_lab(scored: pd.DataFrame, widths: list[float]) -> pd.DataFrame:
    base = pd.to_numeric(scored["forecast_return_365_equivalent"], errors="coerce")
    realized = pd.to_numeric(scored["realized_return"], errors="coerce")
    years = pd.to_numeric(scored["horizon_days"], errors="coerce") / 365.0
    records: list[dict[str, object]] = []
    for width in widths:
        downside = np.maximum(-0.95, base - width)
        upside = base + width
        lower = annual_to_horizon(downside, years)
        upper = annual_to_horizon(upside, years)
        inside = (realized >= lower) & (realized <= upper)
        for horizon, idx in scored.groupby("horizon_days").groups.items():
            mask = scored.index.isin(idx)
            records.append({
                "horizon_days": int(horizon),
                "scenario_width": float(width),
                "case_count": int(mask.sum()),
                "coverage_rate": float(inside[mask].mean()),
                "below_downside_rate": float((realized[mask] < lower[mask]).mean()),
                "above_upside_rate": float((realized[mask] > upper[mask]).mean()),
            })
    return pd.DataFrame(records).sort_values(["horizon_days", "scenario_width"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    scored = pd.read_csv(SOURCE / "collector_walk_forward_phase_2a_scored_outcomes.csv", low_memory=False)
    scored["decision_cutoff"] = pd.to_datetime(scored["decision_cutoff"], errors="coerce")
    variant_rows = build_variant_rates(scored, cfg)
    variant_summary = summarize_variants(variant_rows)
    scenarios = scenario_lab(scored, [float(x) for x in cfg["scenario_width_variants"]])

    best = variant_summary.sort_values(["horizon_days", "mean_absolute_error"]).groupby("horizon_days", as_index=False).first()
    current = variant_summary[variant_summary["variant_name"] == "MODEL_CURRENT"][["horizon_days", "mean_absolute_error"]].rename(columns={"mean_absolute_error": "current_model_mae"})
    recommendations = best.merge(current, on="horizon_days", how="left")
    recommendations["mae_improvement_vs_current"] = recommendations["current_model_mae"] - recommendations["mean_absolute_error"]
    recommendations["recommendation_status"] = np.where(
        (recommendations["case_count"] >= int(cfg["minimum_cases_for_recommendation"])) & (recommendations["mae_improvement_vs_current"] > 0),
        "SHADOW_VARIANT_OUTPERFORMS_CURRENT",
        "CURRENT_NOT_OUTPERFORMED_OR_SAMPLE_INSUFFICIENT",
    )

    state_rows: list[dict[str, object]] = []
    for (horizon, state), g in scored.groupby(["horizon_days", "test_only_decision_state"]):
        state_rows.append({
            "horizon_days": int(horizon),
            "decision_state": state,
            "case_count": int(len(g)),
            "mean_realized_return": float(pd.to_numeric(g["realized_return"], errors="coerce").mean()),
            "median_realized_return": float(pd.to_numeric(g["realized_return"], errors="coerce").median()),
            "mean_absolute_error": float(pd.to_numeric(g["absolute_return_error"], errors="coerce").mean()),
        })
    state_summary = pd.DataFrame(state_rows).sort_values(["horizon_days", "decision_state"])

    failures: list[str] = []
    if scored.empty:
        failures.append("no_phase_2a_scored_outcomes")
    if variant_summary.empty:
        failures.append("no_variant_metrics")
    if scenarios.empty:
        failures.append("no_scenario_metrics")
    if cfg.get("candidate_methodology_change_authorized"):
        failures.append("candidate_methodology_change_must_remain_unauthorized")

    variant_rows.to_csv(OUT / "collector_walk_forward_phase_2b_variant_outcomes.csv", index=False)
    variant_summary.to_csv(OUT / "collector_walk_forward_phase_2b_variant_summary.csv", index=False)
    scenarios.to_csv(OUT / "collector_walk_forward_phase_2b_scenario_coverage.csv", index=False)
    recommendations.to_csv(OUT / "collector_walk_forward_phase_2b_horizon_recommendations.csv", index=False)
    state_summary.to_csv(OUT / "collector_walk_forward_phase_2b_decision_state_summary.csv", index=False)

    summary = {
        "audit_name": "Collector Walk-Forward Phase 2B Benchmark and Calibration Lab",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "source_scored_outcome_count": int(len(scored)),
        "forecast_variant_count": int(len(cfg["forecast_variants"])),
        "variant_outcome_row_count": int(len(variant_rows)),
        "scenario_width_variant_count": int(len(cfg["scenario_width_variants"])),
        "horizon_recommendation_count": int(len(recommendations)),
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2b_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
