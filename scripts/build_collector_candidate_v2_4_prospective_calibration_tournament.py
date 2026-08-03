from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_4_prospective_calibration_tournament_v1.json"
SOURCE = ROOT / "data/operations/collector_candidate_v2_4_shadow_revalidation/candidate_v2_4_0_shadow"
OUT = ROOT / "data/operations/collector_candidate_v2_4_prospective_calibration_tournament/candidate_v1_0_0"


def assign_terciles(values: pd.Series) -> pd.Series:
    ranks = values.rank(method="first", pct=True)
    return pd.Series(np.where(ranks <= 1/3, "HIGH", np.where(ranks <= 2/3, "MEDIUM", "LOW")), index=values.index)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    pred = pd.read_csv(SOURCE / "collector_candidate_v2_4_shadow_predictions.csv", parse_dates=["decision_cutoff"], low_memory=False)
    for col in ["shadow_forecast_return", "realized_return", "shadow_absolute_error"]:
        pred[col] = pd.to_numeric(pred[col], errors="coerce")
    pred["horizon_days"] = pd.to_numeric(pred["horizon_days"], errors="coerce").astype("Int64")
    pred = pred.dropna(subset=["decision_cutoff", "product_key", "shadow_forecast_return", "realized_return", "shadow_absolute_error", "horizon_days"]).copy()
    pred["outcome_maturity_date"] = pred["decision_cutoff"] + pd.to_timedelta(pred["horizon_days"].astype(int), unit="D")

    confidence_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []

    for horizon, hf in pred.groupby("horizon_days"):
        for cutoff in sorted(hf["decision_cutoff"].unique()):
            test = hf[hf["decision_cutoff"] == cutoff].copy()
            prior = hf[hf["outcome_maturity_date"] < cutoff].copy()
            if len(prior) < int(cfg["minimum_prior_horizon_cases"]):
                continue

            horizon_mae = float(prior["shadow_absolute_error"].mean())
            product_mae = prior.groupby("product_key")["shadow_absolute_error"].agg(["mean", "count"])
            cutoff_median_forecast = float(test["shadow_forecast_return"].median())
            cutoff_scale = float(test["shadow_forecast_return"].mad()) if hasattr(test["shadow_forecast_return"], "mad") else float((test["shadow_forecast_return"] - cutoff_median_forecast).abs().mean())
            cutoff_scale = cutoff_scale if cutoff_scale > 1e-12 else 1.0

            for method in cfg["confidence_methods"]:
                scores = []
                for _, row in test.iterrows():
                    if row["product_key"] in product_mae.index and int(product_mae.loc[row["product_key"], "count"]) >= int(cfg["minimum_prior_product_cases"]):
                        pmae = float(product_mae.loc[row["product_key"], "mean"])
                    else:
                        pmae = horizon_mae
                    extremeness = abs(float(row["shadow_forecast_return"]) - cutoff_median_forecast) / cutoff_scale
                    if method == "PRIOR_PRODUCT_MAE":
                        score = pmae
                    elif method == "PRIOR_PRODUCT_MAE_PLUS_FORECAST_EXTREMENESS":
                        score = pmae + 0.1 * extremeness
                    else:
                        score = horizon_mae + 0.1 * extremeness
                    scores.append(score)
                labels = assign_terciles(pd.Series(scores, index=test.index))
                for idx, row in test.iterrows():
                    confidence_rows.append({
                        "horizon_days": int(horizon),
                        "decision_cutoff": cutoff,
                        "product_key": row["product_key"],
                        "product_name": row["product_name"],
                        "confidence_method": method,
                        "confidence_bucket": labels.loc[idx],
                        "prospective_confidence_score": float(pd.Series(scores, index=test.index).loc[idx]),
                        "shadow_forecast_return": float(row["shadow_forecast_return"]),
                        "realized_return": float(row["realized_return"]),
                        "absolute_error": float(row["shadow_absolute_error"]),
                        "future_information_used": False,
                    })

            if len(test) >= 3:
                for lower_q in cfg["decision_lower_quantiles"]:
                    for upper_q in cfg["decision_upper_quantiles"]:
                        if float(lower_q) >= float(upper_q):
                            continue
                        low = float(test["shadow_forecast_return"].quantile(float(lower_q)))
                        high = float(test["shadow_forecast_return"].quantile(float(upper_q)))
                        state = np.where(test["shadow_forecast_return"] >= high, "FAVORABLE", np.where(test["shadow_forecast_return"] <= low, "NEUTRAL", "WATCH"))
                        for idx, row in test.assign(decision_state=state).iterrows():
                            decision_rows.append({
                                "horizon_days": int(horizon),
                                "decision_cutoff": cutoff,
                                "product_key": row["product_key"],
                                "product_name": row["product_name"],
                                "lower_quantile": float(lower_q),
                                "upper_quantile": float(upper_q),
                                "decision_state": row["decision_state"],
                                "shadow_forecast_return": float(row["shadow_forecast_return"]),
                                "realized_return": float(row["realized_return"]),
                                "absolute_error": float(row["shadow_absolute_error"]),
                                "future_information_used": False,
                            })

    confidence = pd.DataFrame(confidence_rows)
    decisions = pd.DataFrame(decision_rows)

    confidence_summary_rows: list[dict[str, object]] = []
    if not confidence.empty:
        for (horizon, method), g in confidence.groupby(["horizon_days", "confidence_method"]):
            by = g.groupby("confidence_bucket")["absolute_error"].mean().to_dict()
            high, med, low = by.get("HIGH", np.nan), by.get("MEDIUM", np.nan), by.get("LOW", np.nan)
            ordering = bool(pd.notna(high) and pd.notna(med) and pd.notna(low) and high < med < low)
            spread = float(low - high) if pd.notna(low) and pd.notna(high) else np.nan
            confidence_summary_rows.append({
                "horizon_days": int(horizon),
                "confidence_method": method,
                "case_count": int(len(g)),
                "decision_cutoff_count": int(g["decision_cutoff"].nunique()),
                "high_mae": high,
                "medium_mae": med,
                "low_mae": low,
                "ordinal_error_ordering_pass": ordering,
                "low_minus_high_mae_spread": spread,
                "prospective_method": True,
            })
    confidence_summary = pd.DataFrame(confidence_summary_rows)
    if not confidence_summary.empty:
        confidence_summary["confidence_score"] = np.where(confidence_summary["ordinal_error_ordering_pass"], -confidence_summary["low_minus_high_mae_spread"], 1.0)
        confidence_summary["rank_within_horizon"] = confidence_summary.groupby("horizon_days")["confidence_score"].rank(method="dense")

    decision_summary_rows: list[dict[str, object]] = []
    if not decisions.empty:
        for (horizon, lower_q, upper_q), g in decisions.groupby(["horizon_days", "lower_quantile", "upper_quantile"]):
            realized = g.groupby("decision_state")["realized_return"].mean().to_dict()
            fav, watch, neutral = realized.get("FAVORABLE", np.nan), realized.get("WATCH", np.nan), realized.get("NEUTRAL", np.nan)
            ordering = bool(pd.notna(fav) and pd.notna(watch) and pd.notna(neutral) and fav > watch > neutral)
            separation = float(fav - neutral) if pd.notna(fav) and pd.notna(neutral) else np.nan
            decision_summary_rows.append({
                "horizon_days": int(horizon),
                "lower_quantile": float(lower_q),
                "upper_quantile": float(upper_q),
                "case_count": int(len(g)),
                "decision_cutoff_count": int(g["decision_cutoff"].nunique()),
                "favorable_realized_return": fav,
                "watch_realized_return": watch,
                "neutral_realized_return": neutral,
                "ordinal_realized_ordering_pass": ordering,
                "favorable_minus_neutral_spread": separation,
            })
    decision_summary = pd.DataFrame(decision_summary_rows)
    if not decision_summary.empty:
        decision_summary["decision_score"] = np.where(decision_summary["ordinal_realized_ordering_pass"], -decision_summary["favorable_minus_neutral_spread"], 1.0)
        decision_summary["rank_within_horizon"] = decision_summary.groupby("horizon_days")["decision_score"].rank(method="dense")

    confidence_winners = confidence_summary[confidence_summary["ordinal_error_ordering_pass"] == True].sort_values(["horizon_days", "confidence_score"]).groupby("horizon_days").head(1) if not confidence_summary.empty else pd.DataFrame()
    decision_winners = decision_summary[decision_summary["ordinal_realized_ordering_pass"] == True].sort_values(["horizon_days", "decision_score"]).groupby("horizon_days").head(1) if not decision_summary.empty else pd.DataFrame()

    failures: list[str] = []
    if confidence.empty: failures.append("no_confidence_predictions")
    if decisions.empty: failures.append("no_decision_predictions")
    if not confidence.empty and confidence["future_information_used"].any(): failures.append("confidence_future_information_used")
    if not decisions.empty and decisions["future_information_used"].any(): failures.append("decision_future_information_used")
    for key in ["prospective_confidence_method_authorized", "decision_state_method_authorized", "candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed", "technical_freeze_authorized", "uip_acceptance_authorized"]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    confidence.to_csv(OUT / "collector_candidate_v2_4_prospective_confidence_predictions.csv", index=False)
    confidence_summary.to_csv(OUT / "collector_candidate_v2_4_prospective_confidence_summary.csv", index=False)
    confidence_winners.to_csv(OUT / "collector_candidate_v2_4_prospective_confidence_winners.csv", index=False)
    decisions.to_csv(OUT / "collector_candidate_v2_4_decision_threshold_predictions.csv", index=False)
    decision_summary.to_csv(OUT / "collector_candidate_v2_4_decision_threshold_summary.csv", index=False)
    decision_winners.to_csv(OUT / "collector_candidate_v2_4_decision_threshold_winners.csv", index=False)

    result = {
        "audit_name": cfg["audit_name"],
        "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "confidence_prediction_count": int(len(confidence)),
        "confidence_configuration_count": int(len(confidence_summary)),
        "confidence_winner_count": int(len(confidence_winners)),
        "decision_prediction_count": int(len(decisions)),
        "decision_configuration_count": int(len(decision_summary)),
        "decision_winner_count": int(len(decision_winners)),
        "shadow_only": True,
        "prospective_confidence_method_authorized": False,
        "decision_state_method_authorized": False,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_candidate_v2_4_prospective_calibration_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
