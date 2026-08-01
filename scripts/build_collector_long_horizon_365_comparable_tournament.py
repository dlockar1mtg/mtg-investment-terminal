from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_long_horizon_365_comparable_tournament_v1.json"
OUT = ROOT / "data/operations/collector_long_horizon_365_comparable_tournament/candidate_v1_0_0"


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def choose(df: pd.DataFrame, aliases: list[str]) -> str | None:
    cols = {str(c).lower(): str(c) for c in df.columns}
    return next((cols[a.lower()] for a in aliases if a.lower() in cols), None)


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def metric_rows(frame: pd.DataFrame, forecast_col: str, label: str, extra: dict[str, object]) -> dict[str, object]:
    valid = frame.dropna(subset=[forecast_col, "realized_return_365"]).copy()
    if valid.empty:
        return {**extra, "variant": label, "case_count": 0, "cutoff_count": 0}
    err = valid[forecast_col] - valid["realized_return_365"]
    direction = np.sign(valid[forecast_col]) == np.sign(valid["realized_return_365"])
    rank = valid[[forecast_col, "realized_return_365"]].corr(method="spearman").iloc[0, 1] if len(valid) > 2 else np.nan
    valid["forecast_rank"] = valid.groupby("decision_cutoff")[forecast_col].rank(pct=True)
    top = valid.loc[valid["forecast_rank"] >= 0.8, "realized_return_365"].mean()
    bottom = valid.loc[valid["forecast_rank"] <= 0.2, "realized_return_365"].mean()
    cutoff_mae = valid.assign(abs_error=err.abs()).groupby("decision_cutoff")["abs_error"].mean()
    trimmed = valid.assign(abs_error=err.abs()).sort_values("abs_error").iloc[: max(1, int(len(valid) * 0.95))]
    return {
        **extra,
        "variant": label,
        "case_count": int(len(valid)),
        "cutoff_count": int(valid["decision_cutoff"].nunique()),
        "mae": float(err.abs().mean()),
        "median_absolute_error": float(err.abs().median()),
        "signed_bias": float(err.mean()),
        "direction_accuracy": float(direction.mean()),
        "rank_correlation": float(rank) if pd.notna(rank) else np.nan,
        "top_bottom_spread": float(top - bottom) if pd.notna(top) and pd.notna(bottom) else np.nan,
        "cutoff_mae_std": float(cutoff_mae.std(ddof=1)) if len(cutoff_mae) > 1 else np.nan,
        "trimmed_95_mae": float((trimmed[forecast_col] - trimmed["realized_return_365"]).abs().mean()),
        "outlier_mae_delta": float(err.abs().mean() - (trimmed[forecast_col] - trimmed["realized_return_365"]).abs().mean()),
    }


def standardize_outcomes(raw: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    if raw.empty:
        return pd.DataFrame(), None
    key = choose(raw, ["product_key", "tcgplayer_product_id", "product_id"])
    name = choose(raw, ["product_name", "name"])
    cutoff = choose(raw, ["decision_cutoff"])
    horizon = choose(raw, ["horizon_days", "forecast_horizon_days"])
    realized = choose(raw, ["realized_return", "actual_return", "outcome_return", "realized_return_365"])
    baseline = choose(raw, [
        "forecast_return_365_equivalent",
        "forecast_return_365",
        "current_forecast_return_365",
        "baseline_forecast_return_365",
        "point_forecast_return_365",
        "predicted_return_365",
        "forecast_return",
        "baseline_forecast_return",
        "current_forecast_return",
        "shadow_forecast_return",
        "predicted_return",
        "point_forecast_return",
    ])
    if cutoff is None or realized is None or (key is None and name is None):
        return pd.DataFrame(), baseline
    out = pd.DataFrame({
        "product_key": raw[key].astype(str) if key else "",
        "product_name": raw[name].astype(str) if name else "",
        "decision_cutoff": pd.to_datetime(raw[cutoff], errors="coerce").dt.strftime("%Y-%m-%d"),
        "horizon_days": num(raw[horizon]) if horizon else 365,
        "realized_return_365": num(raw[realized]),
        "current_forecast_return_365": num(raw[baseline]) if baseline else np.nan,
    })
    return out[out["horizon_days"] == 365].dropna(subset=["decision_cutoff", "realized_return_365"]), baseline


def comparable_predictions(data: pd.DataFrame, minimum: int, maximum: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    features = [
        "product_age_months", "return_3_month", "return_6_month", "trailing_12_month_volatility",
        "maximum_12_month_drawdown", "positive_month_rate", "return_persistence",
    ]
    details: list[dict[str, object]] = []
    predictions: list[dict[str, object]] = []
    for cutoff, block in data.groupby("decision_cutoff"):
        matured = block.dropna(subset=["realized_return_365"]).copy()
        if len(matured) < minimum + 1:
            continue
        med = matured[features].median(numeric_only=True)
        scale = (matured[features].apply(pd.to_numeric, errors="coerce") - med).abs().mean()
        scale = scale.replace(0, np.nan).fillna(1.0)
        for idx, target in matured.iterrows():
            pool = matured.drop(index=idx).copy()
            target_vec = pd.to_numeric(target[features], errors="coerce")
            z = (pool[features].apply(pd.to_numeric, errors="coerce") - target_vec) / scale
            pool["distance"] = np.sqrt((z.fillna(0.0) ** 2).mean(axis=1))
            peers = pool.sort_values("distance").head(maximum)
            if len(peers) < minimum:
                continue
            weights = 1.0 / (1.0 + peers["distance"])
            pred = float(np.average(peers["realized_return_365"], weights=weights))
            hist = float(target.get("history_observation_count", 0) or 0)
            route = "BLENDED" if hist >= 9 else "COMPARABLE" if hist >= 6 else "BLOCKED"
            product_signal = pd.to_numeric(pd.Series([target.get("return_12_month")]), errors="coerce").iloc[0]
            if route == "BLENDED" and pd.notna(product_signal):
                pred = 0.4 * float(product_signal) + 0.6 * pred
            predictions.append({
                "product_key": target["product_key"], "product_name": target["product_name"],
                "decision_cutoff": cutoff, "forecast_route": route,
                "comparable_forecast_return_365": pred if route != "BLOCKED" else np.nan,
                "realized_return_365": target["realized_return_365"],
                "comparable_count": int(len(peers)),
                "uncertainty_multiplier": 1.25 if route == "BLENDED" else 1.6 if route == "COMPARABLE" else np.nan,
                "evidence_grade": "B_VINTAGE_REPLAY" if route == "BLENDED" else "C_PROXY_PRIOR" if route == "COMPARABLE" else "BLOCKED",
            })
            for rank, (_, peer) in enumerate(peers.iterrows(), start=1):
                details.append({
                    "target_product_key": target["product_key"], "target_product": target["product_name"],
                    "decision_cutoff": cutoff, "comparable_rank": rank,
                    "comparable_product_key": peer["product_key"], "comparable_product": peer["product_name"],
                    "match_distance": float(peer["distance"]),
                    "comparable_weight": float((1.0 / (1.0 + peer["distance"])) / weights.sum()),
                    "comparable_realized_return_365": float(peer["realized_return_365"]),
                })
    return pd.DataFrame(predictions), pd.DataFrame(details)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    features = read_csv(ROOT / cfg["inputs"]["decision_feature_panel"])
    outcomes, current_baseline_source_column = standardize_outcomes(read_csv(ROOT / cfg["inputs"]["walk_forward_outcomes"]))
    if features.empty:
        failures.append("decision_feature_panel_missing_or_empty")
    if outcomes.empty:
        failures.append("matured_365_outcomes_missing_or_unmapped")

    merged = pd.DataFrame()
    if not features.empty and not outcomes.empty:
        for c in ["product_key", "product_name", "decision_cutoff"]:
            features[c] = features[c].astype(str)
            outcomes[c] = outcomes[c].astype(str)
        merged = features.merge(outcomes, on=["product_key", "product_name", "decision_cutoff"], how="inner", suffixes=("", "_outcome"))
        if merged.empty:
            merged = features.merge(outcomes, on=["product_name", "decision_cutoff"], how="inner", suffixes=("", "_outcome"))
    if merged.empty:
        failures.append("feature_outcome_join_empty")

    prediction_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    if not merged.empty:
        merged["product_signal"] = num(merged["return_12_month"])
        merged["category_signal"] = num(merged["collector_category_cagr"])
        merged["volatility"] = num(merged["trailing_12_month_volatility"]).fillna(0)
        merged["drawdown"] = num(merged["maximum_12_month_drawdown"]).fillna(0).abs()
        merged["persistence"] = num(merged["return_persistence"]).fillna(0)
        merged["no_change_forecast"] = 0.0
        merged["category_forecast"] = merged["category_signal"]
        summary_rows.append(metric_rows(merged, "current_forecast_return_365", "CURRENT_365", {
            "variant_type": "BASELINE", "source_column": current_baseline_source_column or "UNMAPPED",
        }))
        summary_rows.append(metric_rows(merged, "no_change_forecast", "NO_CHANGE", {"variant_type": "BASELINE"}))
        summary_rows.append(metric_rows(merged, "category_forecast", "CATEGORY_MEDIAN", {"variant_type": "BASELINE"}))

        dcfg = cfg["direct_tournament"]
        for pw, mr, vp, dp, pa in itertools.product(
            dcfg["product_weights"], dcfg["mean_reversion_strengths"], dcfg["volatility_penalties"],
            dcfg["drawdown_penalties"], dcfg["persistence_adjustments"],
        ):
            work = merged.copy()
            raw = pw * work["product_signal"] + (1.0 - pw) * work["category_signal"]
            reverted = work["category_signal"] + mr * (raw - work["category_signal"])
            work["candidate_forecast_return_365"] = reverted - vp * work["volatility"] - dp * work["drawdown"] + pa * work["persistence"]
            label = f"PW{pw}_MR{mr}_VP{vp}_DP{dp}_PA{pa}"
            extra = {"variant_type": "DIRECT_CHALLENGER", "product_weight": pw, "mean_reversion_strength": mr, "volatility_penalty": vp, "drawdown_penalty": dp, "persistence_adjustment": pa}
            summary_rows.append(metric_rows(work, "candidate_forecast_return_365", label, extra))
            prediction_rows.append(work[["product_key", "product_name", "decision_cutoff", "candidate_forecast_return_365", "realized_return_365"]].assign(variant=label))

    summary = pd.DataFrame(summary_rows)
    if not summary.empty and "mae" in summary:
        summary["rank_by_mae"] = summary["mae"].rank(method="min")
        summary = summary.sort_values(["mae", "signed_bias"], na_position="last")
    predictions = pd.concat(prediction_rows, ignore_index=True) if prediction_rows else pd.DataFrame()

    current_row = summary.loc[summary.get("variant", pd.Series(dtype=str)).eq("CURRENT_365")]
    current_baseline_case_count = int(current_row["case_count"].iloc[0]) if not current_row.empty else 0
    current_baseline_comparable = current_baseline_case_count > 0
    if not current_baseline_comparable:
        failures.append("current_365_baseline_unmapped_or_empty")

    comp_predictions, comp_details = comparable_predictions(
        merged, cfg["comparable_transfer"]["minimum_comparables"], cfg["comparable_transfer"]["maximum_comparables"]
    ) if not merged.empty else (pd.DataFrame(), pd.DataFrame())
    comp_summary = pd.DataFrame()
    if not comp_predictions.empty:
        rows = []
        for route, block in comp_predictions.groupby("forecast_route"):
            rows.append(metric_rows(block, "comparable_forecast_return_365", f"COMPARABLE_{route}", {"forecast_route": route}))
        rows.append(metric_rows(comp_predictions, "comparable_forecast_return_365", "COMPARABLE_ALL", {"forecast_route": "ALL"}))
        comp_summary = pd.DataFrame(rows)

    summary.to_csv(OUT / "collector_365_direct_tournament_summary.csv", index=False)
    predictions.to_csv(OUT / "collector_365_direct_tournament_predictions.csv", index=False)
    comp_predictions.to_csv(OUT / "collector_365_comparable_transfer_predictions.csv", index=False)
    comp_details.to_csv(OUT / "collector_365_comparable_matches.csv", index=False)
    comp_summary.to_csv(OUT / "collector_365_comparable_transfer_summary.csv", index=False)

    winner_count = int((summary.get("rank_by_mae", pd.Series(dtype=float)) == 1).sum()) if not summary.empty else 0
    if summary.empty:
        failures.append("direct_tournament_empty")
    if comp_predictions.empty:
        failures.append("comparable_transfer_backtest_empty")
    result = {
        "audit_name": cfg["program_name"], "audit_version": "1.0.1",
        "status": "PASS" if not failures else "FAIL",
        "direct_variant_count": int(len(summary)), "direct_prediction_count": int(len(predictions)),
        "direct_winner_count": winner_count, "comparable_prediction_count": int(len(comp_predictions)),
        "comparable_match_count": int(len(comp_details)), "comparable_route_count": int(comp_predictions["forecast_route"].nunique()) if not comp_predictions.empty else 0,
        "current_baseline_source_column": current_baseline_source_column,
        "current_baseline_case_count": current_baseline_case_count,
        "current_baseline_comparable": current_baseline_comparable,
        "owner_review_required": True,
        "direct_owner_review_eligible": bool(current_baseline_comparable and not failures),
        "comparable_owner_review_eligible": bool(not comp_predictions.empty),
        "shadow_only": True,
        "direct_method_authorized": False, "comparable_transfer_method_authorized": False,
        "candidate_methodology_change_authorized": False, "production_projection_authorized": False,
        "purchase_recommendation_authorized": False, "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False, "uip_acceptance_authorized": False,
        "failure_count": len(failures), "failures": failures,
    }
    (OUT / "collector_long_horizon_365_comparable_tournament_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
