from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/mtg/governance/collector_early_lifecycle_feature_tournament_v1.json"


def safe_corr(a: pd.Series, b: pd.Series) -> float:
    valid = pd.concat([a, b], axis=1).dropna()
    return float(valid.iloc[:, 0].corr(valid.iloc[:, 1], method="spearman")) if len(valid) >= 3 else np.nan


def price_band(value: float) -> str:
    if not math.isfinite(value):
        return "UNKNOWN"
    if value < 180:
        return "UNDER_180"
    if value < 250:
        return "180_TO_249"
    if value < 350:
        return "250_TO_349"
    if value < 500:
        return "350_TO_499"
    return "500_PLUS"


def top_bottom_spread(frame: pd.DataFrame) -> float:
    if len(frame) < 5:
        return np.nan
    ranked = frame.sort_values("candidate_signal")
    n = max(1, int(math.ceil(len(ranked) * 0.20)))
    return float(ranked.tail(n)["realized_return_365"].mean() - ranked.head(n)["realized_return_365"].mean())


def score_metrics(frame: pd.DataFrame, thresholds: list[float]) -> dict[str, object]:
    result: dict[str, object] = {
        "case_count": int(len(frame)),
        "product_count": int(frame["product_key"].nunique()),
        "cutoff_count": int(frame["decision_cutoff"].nunique()),
        "mae": float((frame["candidate_signal"] - frame["realized_return_365"]).abs().mean()),
        "signed_error": float((frame["candidate_signal"] - frame["realized_return_365"]).mean()),
        "rank_correlation": safe_corr(frame["candidate_signal"], frame["realized_return_365"]),
        "top_bottom_spread": top_bottom_spread(frame),
    }
    top_n = max(1, int(math.ceil(len(frame) * 0.20)))
    top_idx = set(frame.nlargest(top_n, "candidate_signal").index)
    for threshold in thresholds:
        tag = int(round(threshold * 100))
        actual = frame["realized_return_365"] >= threshold
        predicted = frame["candidate_signal"] >= threshold
        positives = int(actual.sum())
        negatives = int((~actual).sum())
        tp = int((actual & predicted).sum())
        fn = int((actual & ~predicted).sum())
        fp = int((~actual & predicted).sum())
        captured = int(sum(i in top_idx for i in frame.index[actual]))
        missed = frame.loc[actual & ~predicted, "realized_return_365"] - frame.loc[actual & ~predicted, "candidate_signal"]
        result[f"breakout_count_{tag}"] = positives
        result[f"breakout_recall_{tag}"] = tp / positives if positives else np.nan
        result[f"false_negative_rate_{tag}"] = fn / positives if positives else np.nan
        result[f"top_quantile_capture_{tag}"] = captured / positives if positives else np.nan
        result[f"false_positive_rate_{tag}"] = fp / negatives if negatives else np.nan
        result[f"mean_missed_upside_{tag}"] = float(missed.mean()) if not missed.empty else 0.0
    return result


def expanding_priors(frame: pd.DataFrame, minimum_prior_cases: int) -> pd.DataFrame:
    work = frame.sort_values(["decision_cutoff", "product_name"]).copy()
    age_prior: list[float] = []
    age_price_prior: list[float] = []
    age_counts: list[int] = []
    age_price_counts: list[int] = []
    for _, row in work.iterrows():
        prior = work[work["decision_cutoff"] < row["decision_cutoff"]]
        age_peer = prior[prior["early_lifecycle_band"] == row["early_lifecycle_band"]]
        price_peer = age_peer[age_peer["price_band"] == row["price_band"]]
        age_counts.append(int(len(age_peer)))
        age_price_counts.append(int(len(price_peer)))
        age_prior.append(float(age_peer["realized_return_365"].median()) if len(age_peer) >= minimum_prior_cases else np.nan)
        age_price_prior.append(float(price_peer["realized_return_365"].median()) if len(price_peer) >= minimum_prior_cases else np.nan)
    work["expanding_age_prior"] = age_prior
    work["expanding_age_price_prior"] = age_price_prior
    work["expanding_age_prior_count"] = age_counts
    work["expanding_age_price_prior_count"] = age_price_counts
    return work


def calibrate_rank_to_prior_returns(
    frame: pd.DataFrame,
    raw_score: pd.Series,
    minimum_prior_cases: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    calibrated = pd.Series(np.nan, index=frame.index, dtype=float)
    percentile = pd.Series(np.nan, index=frame.index, dtype=float)
    prior_count = pd.Series(0, index=frame.index, dtype=int)
    for cutoff, current in frame.groupby("decision_cutoff", sort=True):
        prior = frame[frame["decision_cutoff"] < cutoff]["realized_return_365"].dropna().astype(float)
        prior_count.loc[current.index] = int(len(prior))
        if len(prior) < minimum_prior_cases:
            continue
        scores = pd.to_numeric(raw_score.loc[current.index], errors="coerce")
        valid = scores.dropna()
        if valid.empty:
            continue
        ranks = valid.rank(method="average", pct=True)
        percentile.loc[ranks.index] = ranks
        prior_values = np.sort(prior.to_numpy(dtype=float))
        calibrated.loc[ranks.index] = [
            float(np.quantile(prior_values, min(max(float(p), 0.0), 1.0), method="linear"))
            for p in ranks
        ]
    return calibrated, percentile, prior_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    source = ROOT / cfg["inputs"]["breakout_replay_cases"]
    out = ROOT / cfg["output_root"]
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    try:
        cases = pd.read_csv(source, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        cases = pd.DataFrame()
    if cases.empty:
        failures.append("breakout_replay_cases_missing_or_empty")

    required = {"product_key", "product_name", "decision_cutoff", "early_lifecycle_band", "forecast_signal", "realized_return_365"}
    if not cases.empty and not required.issubset(cases.columns):
        failures.append("required_replay_fields_missing")

    predictions = pd.DataFrame()
    leaderboard = pd.DataFrame()
    if not failures:
        cases["decision_cutoff"] = pd.to_datetime(cases["decision_cutoff"], errors="coerce")
        cases["forecast_signal"] = pd.to_numeric(cases["forecast_signal"], errors="coerce")
        cases["realized_return_365"] = pd.to_numeric(cases["realized_return_365"], errors="coerce")
        current_price = pd.to_numeric(cases.get("current_price_at_cutoff", pd.Series(np.nan, index=cases.index)), errors="coerce")
        cases["price_band"] = current_price.map(price_band)
        cases = cases.dropna(subset=["decision_cutoff", "forecast_signal", "realized_return_365"]).copy()
        base = expanding_priors(cases, int(cfg["minimum_prior_cases"]))
        universal_prior = base["realized_return_365"].expanding(min_periods=int(cfg["minimum_prior_cases"])).median().shift(1)
        age = base["expanding_age_prior"].fillna(universal_prior)
        age_price = base["expanding_age_price_prior"].fillna(age)

        raw_map = {
            "MOMENTUM_MEDIAN_BASELINE": base["forecast_signal"],
            "CONTRARIAN_MOMENTUM": -base["forecast_signal"],
            "EXPANDING_AGE_PRIOR": age,
            "EXPANDING_AGE_PRICE_PRIOR": age_price,
            "CONTRARIAN_AGE_BLEND_50_50": 0.50 * (-base["forecast_signal"]) + 0.50 * age,
            "CONTRARIAN_AGE_PRICE_BLEND_50_50": 0.50 * (-base["forecast_signal"]) + 0.50 * age_price,
            "CONTRARIAN_AGE_PRICE_BLEND_25_75": 0.25 * (-base["forecast_signal"]) + 0.75 * age_price,
        }

        rows: list[pd.DataFrame] = []
        metrics_rows: list[dict[str, object]] = []
        thresholds = [float(x) for x in cfg["breakout_thresholds"]]
        minimum_prior_cases = int(cfg["minimum_prior_cases"])
        for method, raw_score in raw_map.items():
            candidate = base.copy()
            candidate["candidate_method"] = method
            candidate["raw_ranking_score"] = pd.to_numeric(raw_score, errors="coerce")
            calibrated, percentile, prior_count = calibrate_rank_to_prior_returns(
                candidate,
                candidate["raw_ranking_score"],
                minimum_prior_cases,
            )
            candidate["ranking_percentile_at_cutoff"] = percentile
            candidate["calibration_prior_count"] = prior_count
            candidate["candidate_signal"] = calibrated
            candidate["point_forecast_calibration"] = "EXPANDING_PRIOR_RETURN_QUANTILE"
            candidate = candidate.dropna(subset=["raw_ranking_score", "candidate_signal"]).copy()
            candidate["future_information_used"] = False
            rows.append(candidate)
            metrics_rows.append({"candidate_method": method, **score_metrics(candidate, thresholds)})

        predictions = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        leaderboard = pd.DataFrame(metrics_rows)
        if not leaderboard.empty:
            leaderboard["qualification_flag"] = (
                (leaderboard["rank_correlation"] > 0) &
                (leaderboard["top_bottom_spread"] > 0) &
                (leaderboard["breakout_recall_70"] > 0)
            )
            leaderboard["selection_score"] = (
                leaderboard["rank_correlation"].fillna(-1.0) +
                leaderboard["top_bottom_spread"].fillna(-1.0) +
                leaderboard["breakout_recall_70"].fillna(0.0) +
                leaderboard["top_quantile_capture_70"].fillna(0.0) -
                leaderboard["false_negative_rate_70"].fillna(1.0) -
                0.25 * leaderboard["false_positive_rate_50"].fillna(0.0)
            )
            leaderboard = leaderboard.sort_values(["qualification_flag", "selection_score"], ascending=[False, False])

    if predictions.empty:
        failures.append("no_tournament_predictions")
    if leaderboard.empty:
        failures.append("no_tournament_metrics")

    predictions.to_csv(out / "collector_early_lifecycle_feature_tournament_predictions.csv", index=False)
    leaderboard.to_csv(out / "collector_early_lifecycle_feature_tournament_leaderboard.csv", index=False)

    qualified = int(leaderboard["qualification_flag"].sum()) if not leaderboard.empty else 0
    best_method = str(leaderboard.iloc[0]["candidate_method"]) if not leaderboard.empty else "NOT_AVAILABLE"
    result = {
        "audit_name": cfg["program_name"],
        "audit_version": cfg["program_version"],
        "ranking_return_separation_required": True,
        "point_forecast_calibration_contract": "EXPANDING_PRIOR_RETURN_QUANTILE",
        "candidate_count": int(leaderboard["candidate_method"].nunique()) if not leaderboard.empty else 0,
        "prediction_row_count": int(len(predictions)),
        "qualified_candidate_count": qualified,
        "best_candidate_by_diagnostic_score": best_method,
        "owner_review_required": True,
        "future_information_used": False,
        "methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    (out / "collector_early_lifecycle_feature_tournament_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
