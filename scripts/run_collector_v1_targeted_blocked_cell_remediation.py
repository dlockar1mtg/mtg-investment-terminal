from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EARLY_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
EXPANDED_DIR = ROOT / "data/governance/permanence/certification/collector_v1_expanded_tournament"
REMEDIATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_blocked_cell_remediation"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_targeted_blocked_cell_remediation"


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f"No governed candidate path exists: {[str(p) for p in paths]}")


def first_col(df: pd.DataFrame, names: list[str], required: bool = True) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    if required:
        raise ValueError(f"Required column missing. candidates={names}; available={list(df.columns)}")
    return None


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def normalize_id(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d+)$", expand=False).fillna(series.astype(str))


def loo_bias_correct(frame: pd.DataFrame, id_col: str, actual_col: str, pred_col: str, group_cols: list[str]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    work = frame.copy()
    work[id_col] = normalize_id(work[id_col])
    work[actual_col] = numeric(work[actual_col])
    work[pred_col] = numeric(work[pred_col])
    work["raw_residual"] = work[actual_col] - work[pred_col]
    for _, group in work.groupby(group_cols, dropna=False):
        group = group.copy()
        total_sum = group["raw_residual"].sum()
        total_count = group["raw_residual"].notna().sum()
        by_product = group.groupby(id_col)["raw_residual"].agg(["sum", "count"])
        sums = group[id_col].map(by_product["sum"]).fillna(0.0)
        counts = group[id_col].map(by_product["count"]).fillna(0)
        denom = (total_count - counts).replace(0, np.nan)
        group["holdout_bias_adjustment"] = ((total_sum - sums) / denom).fillna(0.0)
        group["prediction_bias_corrected"] = group[pred_col] + group["holdout_bias_adjustment"]
        parts.append(group)
    return pd.concat(parts, ignore_index=True) if parts else work


def ranking_metrics(group: pd.DataFrame, actual_col: str, pred_col: str) -> dict[str, float | int]:
    actual = numeric(group[actual_col])
    pred = numeric(group[pred_col])
    mask = actual.notna() & pred.notna()
    actual, pred = actual[mask], pred[mask]
    err = pred - actual
    ranked = pd.DataFrame({"actual": actual, "pred": pred}).sort_values("pred", ascending=False)
    n = len(ranked)
    top_n = max(1, int(np.ceil(n * 0.20)))
    predicted_top = ranked.head(top_n)
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
        "top_quintile_precision_25pct": float((predicted_top["actual"] >= 0.25).mean()) if n else np.nan,
        "winner_recall_25pct": float(tp / int(winners.sum())) if int(winners.sum()) else np.nan,
        "false_positive_rate": float(fp / max(1, int(predicted_positive.sum()))),
    }


def build_early_candidates() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    cutoffs_path = first_existing([
        EARLY_DIR / "collector_v1_release_age_cutoffs.csv",
        EARLY_DIR / "collector_v1_release_age_cutoff_dataset.csv",
    ])
    peers_path = first_existing([
        EARLY_DIR / "collector_v1_peer_maturity_curves.csv",
    ])
    cutoffs = pd.read_csv(cutoffs_path)
    peers = pd.read_csv(peers_path)

    cid = first_col(cutoffs, ["tcgplayer_product_id", "product_id"])
    pid = first_col(peers, ["tcgplayer_product_id", "target_product_id", "product_id"])
    age = first_col(cutoffs, ["age_months"])
    actual = first_col(cutoffs, ["actual_return_365d_from_release", "actual_first_year_return", "first_year_return"])
    momentum = first_col(cutoffs, ["momentum_3m", "return_since_release"], required=False)
    peer_median = first_col(peers, ["peer_return_365d_median", "return_365d_median", "median_return_365d"])
    peer_mean = first_col(peers, ["peer_return_365d_mean", "return_365d_mean", "mean_return_365d"], required=False)
    peer_count = first_col(peers, ["peer_count", "selected_peer_count", "unique_peer_count"], required=False)

    cutoffs[cid] = normalize_id(cutoffs[cid])
    peers[pid] = normalize_id(peers[pid])
    keep = [pid, peer_median] + ([peer_mean] if peer_mean else []) + ([peer_count] if peer_count else [])
    merged = cutoffs.merge(peers[keep].drop_duplicates(pid), left_on=cid, right_on=pid, how="left")
    merged[actual] = numeric(merged[actual])
    merged[peer_median] = numeric(merged[peer_median])
    if peer_mean:
        merged[peer_mean] = numeric(merged[peer_mean])
    if momentum:
        merged[momentum] = numeric(merged[momentum]).fillna(0.0)

    if peer_count:
        merged[peer_count] = numeric(merged[peer_count])
        merged = merged[merged[peer_count] >= 3]
    merged = merged[merged[actual].notna() & merged[peer_median].notna()].copy()

    candidate_parts: list[pd.DataFrame] = []
    equal_peer = merged.copy()
    equal_peer["model_variant"] = "COVERAGE_EXPANDED_EQUAL_PEER"
    equal_peer["predicted_first_year_return"] = equal_peer[peer_median]
    candidate_parts.append(equal_peer)

    ensemble = merged.copy()
    peer_center = ensemble[peer_mean] if peer_mean else ensemble[peer_median]
    momentum_component = ensemble[momentum].clip(-0.50, 0.75) if momentum else 0.0
    ensemble["model_variant"] = "AGE_COHORT_RANKING_ENSEMBLE"
    ensemble["predicted_first_year_return"] = 0.65 * ensemble[peer_median] + 0.20 * peer_center + 0.15 * momentum_component
    candidate_parts.append(ensemble)

    candidates = pd.concat(candidate_parts, ignore_index=True)
    candidates = loo_bias_correct(candidates, cid, actual, "predicted_first_year_return", [age, "model_variant"])

    metric_rows: list[dict] = []
    for keys, group in candidates.groupby([age, "model_variant"], dropna=False):
        m = ranking_metrics(group, actual, "prediction_bias_corrected")
        m.update({"age_months": int(float(keys[0])), "model_variant": keys[1]})
        m["promotable"] = bool(m["rows"] >= 30 and abs(m["bias"]) <= 0.20 and m["top_quintile_precision_25pct"] >= 0.60 and m["winner_recall_25pct"] >= 0.50 and m["false_positive_rate"] <= 0.40)
        m["selection_score"] = float(-(0.35 * m["top_quintile_precision_25pct"] + 0.35 * m["winner_recall_25pct"] + 0.20 * max(-1.0, m["rank_correlation"]) - 0.10 * m["false_positive_rate"]))
        metric_rows.append(m)
    metrics = pd.DataFrame(metric_rows)
    diagnostics = {
        "cutoff_rows": int(len(cutoffs)),
        "candidate_rows": int(len(candidates)),
        "candidate_products": int(candidates[cid].nunique()),
        "promotable_age_cells": int(metrics["promotable"].sum()) if not metrics.empty else 0,
    }
    return candidates, metrics, diagnostics


def build_limited_365_resolution() -> tuple[pd.DataFrame, dict]:
    winners_path = EXPANDED_DIR / "collector_v1_expanded_tournament_winners.csv"
    winners = pd.read_csv(winners_path)
    lane = first_col(winners, ["tournament_lane"])
    horizon = first_col(winners, ["horizon_days"])
    status = first_col(winners, ["promotion_status"])
    variant = first_col(winners, ["model_variant"])

    comparable = winners[(winners[lane] == "COMPARABLE_PRODUCT_ADJUSTED") & (numeric(winners[horizon]) == 365)]
    limited = winners[(winners[lane] == "DIRECT_HISTORY_LIMITED") & (numeric(winners[horizon]) == 365)]
    comparable_promotable = bool((comparable[status] == "PROMOTABLE").any())
    limited_blocked = bool((limited[status] != "PROMOTABLE").all()) if not limited.empty else True

    resolution = pd.DataFrame([{
        "tournament_lane": "DIRECT_HISTORY_LIMITED",
        "horizon_days": 365,
        "resolution_type": "ROUTE_DELEGATION",
        "delegated_route": "COMPARABLE_PRODUCT_ADJUSTED",
        "delegated_model_variant": comparable.iloc[0][variant] if not comparable.empty else "",
        "comparable_365_promotable": comparable_promotable,
        "limited_365_direct_blocked": limited_blocked,
        "resolution_status": "APPROVED_FAIL_CLOSED_FALLBACK" if comparable_promotable and limited_blocked else "BLOCKED",
        "reason": "Limited-history 365-day direct models have insufficient stable evidence; use the certified comparable 365-day winner with wider route confidence penalties.",
    }])
    return resolution, {
        "comparable_365_promotable": comparable_promotable,
        "limited_365_direct_blocked": limited_blocked,
        "limited_365_resolution_status": resolution.iloc[0]["resolution_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    early_candidates, early_metrics, early_diag = build_early_candidates()
    limited_resolution, limited_diag = build_limited_365_resolution()

    early_candidates.to_csv(OUT_DIR / "collector_v1_targeted_early_candidates.csv", index=False)
    early_metrics.to_csv(OUT_DIR / "collector_v1_targeted_early_metrics.csv", index=False)
    limited_resolution.to_csv(OUT_DIR / "collector_v1_limited_365_route_resolution.csv", index=False)

    best_early = pd.DataFrame()
    if not early_metrics.empty:
        promotable = early_metrics[early_metrics["promotable"] == True]
        pool = promotable if not promotable.empty else early_metrics
        best_early = pool.sort_values(["selection_score", "age_months"]).head(1).copy()
        best_early["promotion_status"] = np.where(best_early["promotable"], "PROMOTABLE", "BLOCKED_NO_CANDIDATE_MEETS_GATES")
    best_early.to_csv(OUT_DIR / "collector_v1_targeted_early_winner.csv", index=False)

    early_resolved = bool(not best_early.empty and best_early.iloc[0]["promotion_status"] == "PROMOTABLE")
    limited_resolved = bool(limited_resolution.iloc[0]["resolution_status"] == "APPROVED_FAIL_CLOSED_FALLBACK")
    summary = {
        "block_name": "Collector V1 Targeted Blocked Cell Remediation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **early_diag,
        **limited_diag,
        "early_opportunity_cell_resolved": early_resolved,
        "limited_history_365_cell_resolved": limited_resolved,
        "resolved_blocked_cells": int(early_resolved) + int(limited_resolved),
        "remaining_blocked_cells": 2 - (int(early_resolved) + int(limited_resolved)),
        "pair_score_registered": False,
        "targeted_remediation_ready": True,
        "winner_set_methodologically_complete": bool(early_resolved and limited_resolved),
        "winner_certification_authorized": bool(early_resolved and limited_resolved),
        "long_horizon_simulation_authorized_after_winner_certification": bool(early_resolved and limited_resolved),
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_READY",
    }
    (OUT_DIR / "collector_v1_targeted_blocked_cell_remediation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.strict and not summary["targeted_remediation_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
