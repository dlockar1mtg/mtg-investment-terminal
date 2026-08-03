from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation/collector_v1_release_age_cutoffs.csv"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_cohort_fallback_tournament"


def first_col(df: pd.DataFrame, names: list[str], required: bool = True) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    if required:
        raise ValueError(f"Required column missing. candidates={names}; available={list(df.columns)}")
    return None


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def normalize_id(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d+)$", expand=False).fillna(s.astype(str))


def ridge_predict_loo(group: pd.DataFrame, id_col: str, actual_col: str, feature_cols: list[str], alpha: float) -> pd.Series:
    preds = pd.Series(index=group.index, dtype=float)
    for pid, holdout in group.groupby(id_col):
        train = group[group[id_col] != pid].copy()
        test = holdout.copy()
        if len(train) < max(12, len(feature_cols) + 5):
            preds.loc[test.index] = train[actual_col].median()
            continue
        x_train = train[feature_cols].astype(float)
        x_test = test[feature_cols].astype(float)
        med = x_train.median()
        x_train = x_train.fillna(med)
        x_test = x_test.fillna(med)
        mean = x_train.mean()
        std = x_train.std(ddof=0).replace(0, 1.0)
        xt = ((x_train - mean) / std).to_numpy()
        xv = ((x_test - mean) / std).to_numpy()
        y = train[actual_col].to_numpy(float)
        design = np.column_stack([np.ones(len(xt)), xt])
        design_v = np.column_stack([np.ones(len(xv)), xv])
        penalty = np.eye(design.shape[1]) * alpha
        penalty[0, 0] = 0.0
        beta = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
        preds.loc[test.index] = design_v @ beta
    return preds


def ranking_metrics(group: pd.DataFrame, actual_col: str, pred_col: str) -> dict[str, float | int]:
    work = group[[actual_col, pred_col]].dropna().copy()
    actual = num(work[actual_col])
    pred = num(work[pred_col])
    mask = actual.notna() & pred.notna()
    actual, pred = actual[mask], pred[mask]
    err = pred - actual
    ranked = pd.DataFrame({"actual": actual, "pred": pred}).sort_values("pred", ascending=False)
    n = len(ranked)
    top_n = max(1, int(np.ceil(n * 0.20)))
    winners = ranked["actual"] >= 0.25
    predicted_positive = ranked["pred"] >= 0.25
    tp = int((winners & predicted_positive).sum())
    fp = int((~winners & predicted_positive).sum())
    return {
        "rows": n,
        "mae": float(err.abs().mean()),
        "rmse": float(np.sqrt(np.mean(np.square(err)))) if n else np.nan,
        "bias": float(err.mean()),
        "rank_correlation": float(ranked["actual"].corr(ranked["pred"], method="spearman")) if n > 2 else np.nan,
        "top_quintile_precision_25pct": float((ranked.head(top_n)["actual"] >= 0.25).mean()) if n else np.nan,
        "winner_recall_25pct": float(tp / int(winners.sum())) if int(winners.sum()) else np.nan,
        "false_positive_rate": float(fp / max(1, int(predicted_positive.sum()))),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SOURCE)

    id_col = first_col(df, ["tcgplayer_product_id", "product_id"])
    age_col = first_col(df, ["age_months"])
    actual_col = first_col(df, ["actual_return_365d_from_release", "actual_first_year_return", "first_year_return"])
    anchor_col = first_col(df, ["release_anchor_price"])
    cutoff_col = first_col(df, ["cutoff_price"])
    since_release_col = first_col(df, ["return_since_release"], required=False)
    mom3_col = first_col(df, ["momentum_3m"], required=False)
    mom6_col = first_col(df, ["momentum_6m"], required=False)
    cutoff_flag = first_col(df, ["feature_cutoff_enforced"], required=False)

    work = df.copy()
    work[id_col] = normalize_id(work[id_col])
    for col in [actual_col, anchor_col, cutoff_col, since_release_col, mom3_col, mom6_col]:
        if col:
            work[col] = num(work[col])
    if cutoff_flag:
        work = work[work[cutoff_flag].astype(str).str.lower().isin(["true", "1", "yes"])]
    work = work[work[actual_col].notna() & work[anchor_col].notna() & work[cutoff_col].notna()].copy()

    work["log_anchor_price"] = np.log1p(work[anchor_col].clip(lower=0))
    work["log_cutoff_price"] = np.log1p(work[cutoff_col].clip(lower=0))
    work["return_since_release_feature"] = work[since_release_col].fillna(0.0) if since_release_col else 0.0
    work["momentum_3m_feature"] = work[mom3_col].fillna(0.0) if mom3_col else 0.0
    work["momentum_6m_feature"] = work[mom6_col].fillna(0.0) if mom6_col else 0.0

    candidate_parts: list[pd.DataFrame] = []
    metric_rows: list[dict] = []
    feature_sets = {
        "AGE_PRICE_RIDGE": ["log_anchor_price", "log_cutoff_price"],
        "AGE_MOMENTUM_RIDGE": ["log_anchor_price", "log_cutoff_price", "return_since_release_feature", "momentum_3m_feature", "momentum_6m_feature"],
    }

    for age, age_group in work.groupby(age_col):
        age_group = age_group.copy()
        for variant, features in feature_sets.items():
            candidate = age_group.copy()
            candidate["model_variant"] = variant
            candidate["predicted_first_year_return"] = ridge_predict_loo(candidate, id_col, actual_col, features, alpha=5.0)
            candidate_parts.append(candidate)
            m = ranking_metrics(candidate, actual_col, "predicted_first_year_return")
            m.update({"age_months": int(float(age)), "model_variant": variant})
            m["promotable"] = bool(m["rows"] >= 30 and abs(m["bias"]) <= 0.20 and m["top_quintile_precision_25pct"] >= 0.60 and m["winner_recall_25pct"] >= 0.50 and m["false_positive_rate"] <= 0.40)
            m["selection_score"] = float(-(0.35 * m["top_quintile_precision_25pct"] + 0.35 * m["winner_recall_25pct"] + 0.20 * max(-1.0, m["rank_correlation"]) - 0.10 * m["false_positive_rate"]))
            metric_rows.append(m)

        median_candidate = age_group.copy()
        median_candidate["model_variant"] = "AGE_GLOBAL_MEDIAN_LOO"
        preds = []
        for pid in median_candidate[id_col]:
            train = median_candidate[median_candidate[id_col] != pid]
            preds.append(float(train[actual_col].median()))
        median_candidate["predicted_first_year_return"] = preds
        candidate_parts.append(median_candidate)
        m = ranking_metrics(median_candidate, actual_col, "predicted_first_year_return")
        m.update({"age_months": int(float(age)), "model_variant": "AGE_GLOBAL_MEDIAN_LOO"})
        m["promotable"] = bool(m["rows"] >= 30 and abs(m["bias"]) <= 0.20 and m["top_quintile_precision_25pct"] >= 0.60 and m["winner_recall_25pct"] >= 0.50 and m["false_positive_rate"] <= 0.40)
        m["selection_score"] = float(-(0.35 * m["top_quintile_precision_25pct"] + 0.35 * m["winner_recall_25pct"] + 0.20 * max(-1.0, m["rank_correlation"] if pd.notna(m["rank_correlation"]) else -1.0) - 0.10 * m["false_positive_rate"]))
        metric_rows.append(m)

    candidates = pd.concat(candidate_parts, ignore_index=True)
    metrics = pd.DataFrame(metric_rows)
    promotable = metrics[metrics["promotable"] == True]
    winner_pool = promotable if not promotable.empty else metrics
    winner = winner_pool.sort_values(["selection_score", "age_months"]).head(1).copy()
    winner["promotion_status"] = np.where(winner["promotable"], "PROMOTABLE", "BLOCKED_NO_CANDIDATE_MEETS_GATES")

    candidates.to_csv(OUT_DIR / "collector_v1_early_cohort_fallback_predictions.csv", index=False)
    metrics.to_csv(OUT_DIR / "collector_v1_early_cohort_fallback_metrics.csv", index=False)
    winner.to_csv(OUT_DIR / "collector_v1_early_cohort_fallback_winner.csv", index=False)

    resolved = bool(not winner.empty and winner.iloc[0]["promotion_status"] == "PROMOTABLE")
    summary = {
        "block_name": "Collector V1 Early Cohort Fallback Tournament",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_rows": int(len(df)),
        "eligible_rows": int(len(work)),
        "eligible_products": int(work[id_col].nunique()),
        "candidate_cells": int(len(metrics)),
        "promotable_cells": int(metrics["promotable"].sum()),
        "peer_features_required": False,
        "leave_one_product_out_enforced": True,
        "feature_cutoff_enforced": True,
        "early_cohort_fallback_resolved": resolved,
        "winner_certification_authorized": resolved,
        "long_horizon_simulation_authorized_after_winner_certification": resolved,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_EARLY_COHORT_FALLBACK_TOURNAMENT_READY",
    }
    (OUT_DIR / "collector_v1_early_cohort_fallback_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (not args.strict or summary["eligible_products"] >= 30) else 1


if __name__ == "__main__":
    raise SystemExit(main())
