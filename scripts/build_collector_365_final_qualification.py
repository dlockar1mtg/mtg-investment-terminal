from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_365_final_qualification_v1.json"
OUT = ROOT / "data/operations/collector_365_final_qualification/candidate_v1_0_0"


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def metrics(frame: pd.DataFrame, forecast_col: str) -> dict[str, float | int]:
    valid = frame.dropna(subset=[forecast_col, "realized_return_365"]).copy()
    if valid.empty:
        return {"case_count": 0, "cutoff_count": 0}
    err = pd.to_numeric(valid[forecast_col], errors="coerce") - pd.to_numeric(valid["realized_return_365"], errors="coerce")
    rank = valid[[forecast_col, "realized_return_365"]].corr(method="spearman").iloc[0, 1] if len(valid) > 2 else np.nan
    valid["forecast_rank"] = valid.groupby("decision_cutoff")[forecast_col].rank(pct=True)
    top = pd.to_numeric(valid.loc[valid["forecast_rank"] >= 0.8, "realized_return_365"], errors="coerce").mean()
    bottom = pd.to_numeric(valid.loc[valid["forecast_rank"] <= 0.2, "realized_return_365"], errors="coerce").mean()
    return {
        "case_count": int(len(valid)),
        "cutoff_count": int(valid["decision_cutoff"].nunique()),
        "mae": float(err.abs().mean()),
        "median_absolute_error": float(err.abs().median()),
        "signed_bias": float(err.mean()),
        "direction_accuracy": float((np.sign(valid[forecast_col]) == np.sign(valid["realized_return_365"])).mean()),
        "rank_correlation": float(rank) if pd.notna(rank) else np.nan,
        "top_bottom_spread": float(top - bottom) if pd.notna(top) and pd.notna(bottom) else np.nan,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    direct_summary = read_csv(ROOT / cfg["inputs"]["direct_summary"])
    direct_predictions = read_csv(ROOT / cfg["inputs"]["direct_predictions"])
    comparable = read_csv(ROOT / cfg["inputs"]["comparable_predictions"])
    features = read_csv(ROOT / cfg["inputs"]["decision_feature_panel"])

    if direct_summary.empty or direct_predictions.empty or comparable.empty or features.empty:
        failures.append("required_input_missing_or_empty")

    selected = cfg["selected_direct_variant"]
    selected_direct = direct_predictions[direct_predictions.get("variant", pd.Series(dtype=str)).astype(str).eq(selected)].copy()
    current_row = direct_summary[direct_summary.get("variant", pd.Series(dtype=str)).astype(str).eq("CURRENT_365")]
    current_source = str(current_row.get("source_column", pd.Series([""])).iloc[0]) if not current_row.empty else ""

    current_predictions = pd.DataFrame()
    if not selected_direct.empty and not current_row.empty:
        # Reconstruct current baseline from the common feature/outcome population using the same source already certified by the tournament.
        tournament_root = ROOT / "data/operations/collector_long_horizon_365_comparable_tournament/candidate_v1_0_0"
        outcome_path = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0/collector_walk_forward_phase_2a_scored_outcomes.csv"
        raw = read_csv(outcome_path)
        if current_source in raw.columns:
            current_predictions = raw.copy()
            horizon_col = "horizon_days" if "horizon_days" in current_predictions.columns else "forecast_horizon_days"
            if horizon_col in current_predictions.columns:
                current_predictions = current_predictions[pd.to_numeric(current_predictions[horizon_col], errors="coerce").eq(365)]
            realized_col = next((c for c in ["realized_return", "actual_return", "outcome_return", "realized_return_365"] if c in current_predictions.columns), None)
            if realized_col:
                current_predictions = current_predictions.rename(columns={current_source: "current_forecast_return_365", realized_col: "realized_return_365"})
                current_predictions["decision_cutoff"] = pd.to_datetime(current_predictions["decision_cutoff"], errors="coerce").dt.strftime("%Y-%m-%d")
                keep = [c for c in ["product_key", "product_name", "decision_cutoff", "current_forecast_return_365", "realized_return_365"] if c in current_predictions.columns]
                current_predictions = current_predictions[keep]

    key_cols = ["product_name", "decision_cutoff"]
    common = selected_direct.rename(columns={"candidate_forecast_return_365": "direct_forecast_return_365"})
    common = common.merge(comparable[key_cols + ["comparable_forecast_return_365", "realized_return_365"]], on=key_cols, how="inner", suffixes=("", "_comp"))
    if not current_predictions.empty:
        common = common.merge(current_predictions[key_cols + ["current_forecast_return_365"]], on=key_cols, how="inner")
    common = common.merge(features[key_cols + ["product_age_route", "data_quality_grade"]], on=key_cols, how="left")
    common["realized_return_365"] = pd.to_numeric(common["realized_return_365"], errors="coerce")

    if len(common) < cfg["qualification_rules"]["minimum_common_cases"]:
        failures.append("insufficient_common_cases")
    if common["decision_cutoff"].nunique() < cfg["qualification_rules"]["minimum_common_cutoffs"]:
        failures.append("insufficient_common_cutoffs")

    # Expanding-window bias calibration: each cutoff uses only earlier matured cutoffs.
    calibrated_rows: list[pd.DataFrame] = []
    for method in ["DIRECT", "COMPARABLE"]:
        source_col = "direct_forecast_return_365" if method == "DIRECT" else "comparable_forecast_return_365"
        for shrink in cfg["bias_shrinkage_candidates"]:
            parts = []
            for cutoff in sorted(common["decision_cutoff"].dropna().unique()):
                train = common[common["decision_cutoff"] < cutoff].copy()
                test = common[common["decision_cutoff"] == cutoff].copy()
                prior_bias = 0.0
                if not train.empty:
                    prior_bias = float((pd.to_numeric(train[source_col], errors="coerce") - train["realized_return_365"]).median())
                test["forecast"] = pd.to_numeric(test[source_col], errors="coerce") - shrink * prior_bias
                test["method"] = method
                test["bias_shrinkage"] = shrink
                test["prior_median_bias"] = prior_bias
                parts.append(test)
            calibrated_rows.append(pd.concat(parts, ignore_index=True))

    calibrated = pd.concat(calibrated_rows, ignore_index=True) if calibrated_rows else pd.DataFrame()
    summary_rows = []
    cutoff_rows = []
    route_rows = []
    if not calibrated.empty:
        for (method, shrink), block in calibrated.groupby(["method", "bias_shrinkage"]):
            row = {"method": method, "bias_shrinkage": shrink, **metrics(block, "forecast")}
            summary_rows.append(row)
            for cutoff, sub in block.groupby("decision_cutoff"):
                cutoff_rows.append({"method": method, "bias_shrinkage": shrink, "decision_cutoff": cutoff, **metrics(sub, "forecast")})
            for route, sub in block.groupby("product_age_route", dropna=False):
                route_rows.append({"method": method, "bias_shrinkage": shrink, "product_age_route": route, **metrics(sub, "forecast")})

    summary = pd.DataFrame(summary_rows)
    cutoff = pd.DataFrame(cutoff_rows)
    routes = pd.DataFrame(route_rows)

    if not summary.empty:
        summary["qualified"] = (
            (summary["case_count"] >= cfg["qualification_rules"]["minimum_common_cases"])
            & (summary["cutoff_count"] >= cfg["qualification_rules"]["minimum_common_cutoffs"])
            & (summary["signed_bias"].abs() <= cfg["qualification_rules"]["maximum_absolute_signed_bias"])
            & (summary["rank_correlation"] >= cfg["qualification_rules"]["minimum_rank_correlation"])
            & (summary["top_bottom_spread"] >= cfg["qualification_rules"]["minimum_top_bottom_spread"])
        )
        summary = summary.sort_values(["qualified", "mae", "signed_bias"], ascending=[False, True, False])

    summary.to_csv(OUT / "collector_365_final_qualification_summary.csv", index=False)
    calibrated.to_csv(OUT / "collector_365_final_qualification_predictions.csv", index=False)
    cutoff.to_csv(OUT / "collector_365_final_qualification_cutoff_stability.csv", index=False)
    routes.to_csv(OUT / "collector_365_final_qualification_route_stability.csv", index=False)

    qualified_count = int(summary.get("qualified", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").sum()) if not summary.empty else 0
    result = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "status": "PASS" if not failures else "FAIL",
        "selected_direct_variant": selected,
        "common_case_count": int(len(common)),
        "common_cutoff_count": int(common["decision_cutoff"].nunique()) if not common.empty else 0,
        "qualification_variant_count": int(len(summary)),
        "qualified_variant_count": qualified_count,
        "owner_review_required": True,
        "shadow_only": True,
        "direct_method_authorized": False,
        "comparable_transfer_method_authorized": False,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_365_final_qualification_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
