from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EARLY_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
REMEDIATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_blocked_cell_remediation"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_coverage_adjudication"


def first_col(df: pd.DataFrame, names: list[str], required: bool = True) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    if required:
        raise ValueError(f"Required column missing. candidates={names}; available={list(df.columns)}")
    return None


def normalize_id(series: pd.Series) -> pd.Series:
    text = series.astype(str)
    return text.str.extract(r"(\d+)$", expand=False).fillna(text)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cutoff_path = EARLY_DIR / "collector_v1_release_age_cutoffs.csv"
    reconciliation_path = REMEDIATION_DIR / "collector_v1_early_coverage_reconciliation.csv"
    if not cutoff_path.exists():
        raise FileNotFoundError(cutoff_path)

    cutoffs = pd.read_csv(cutoff_path)
    reconciliation = pd.read_csv(reconciliation_path) if reconciliation_path.exists() else pd.DataFrame()

    id_col = first_col(cutoffs, ["tcgplayer_product_id", "product_id"])
    age_col = first_col(cutoffs, ["age_months"])
    actual_col = first_col(cutoffs, ["actual_return_365d_from_release", "actual_first_year_return", "first_year_return"])
    peer_count_col = first_col(cutoffs, ["peer_count", "selected_peer_count", "unique_peer_count"], required=False)
    peer_median_col = first_col(cutoffs, ["peer_return_365d_median", "return_365d_median", "median_return_365d"], required=False)
    peer_mean_col = first_col(cutoffs, ["peer_return_365d_mean", "return_365d_mean", "mean_return_365d"], required=False)
    cutoff_price_col = first_col(cutoffs, ["cutoff_price", "price_at_cutoff"], required=False)
    feature_cutoff_col = first_col(cutoffs, ["feature_cutoff_enforced"], required=False)

    cutoffs[id_col] = normalize_id(cutoffs[id_col])
    cutoffs[actual_col] = numeric(cutoffs[actual_col])
    if peer_count_col:
        cutoffs[peer_count_col] = numeric(cutoffs[peer_count_col])
    if peer_median_col:
        cutoffs[peer_median_col] = numeric(cutoffs[peer_median_col])
    if peer_mean_col:
        cutoffs[peer_mean_col] = numeric(cutoffs[peer_mean_col])
    if cutoff_price_col:
        cutoffs[cutoff_price_col] = numeric(cutoffs[cutoff_price_col])

    rows: list[dict] = []
    for product_id, group in cutoffs.groupby(id_col, dropna=False):
        ages = sorted({int(float(v)) for v in numeric(group[age_col]).dropna().tolist()})
        actual_complete = bool(group[actual_col].notna().all())
        peer_count_complete = bool(peer_count_col and group[peer_count_col].notna().all())
        peer_count_min = float(group[peer_count_col].min()) if peer_count_col and group[peer_count_col].notna().any() else None
        peer_count_gate = bool(peer_count_min is not None and peer_count_min >= 3)
        peer_median_complete = bool(peer_median_col and group[peer_median_col].notna().all())
        peer_mean_complete = bool(peer_mean_col and group[peer_mean_col].notna().all())
        cutoff_price_complete = bool(not cutoff_price_col or group[cutoff_price_col].notna().all())
        feature_cutoff_pass = bool(not feature_cutoff_col or group[feature_cutoff_col].astype(str).str.lower().isin(["true", "1", "yes"]).all())

        eligible = actual_complete and peer_count_gate and peer_median_complete and cutoff_price_complete and feature_cutoff_pass
        reasons: list[str] = []
        if not actual_complete:
            reasons.append("MISSING_REALIZED_FIRST_YEAR_RETURN")
        if not peer_count_complete:
            reasons.append("MISSING_PEER_COUNT")
        elif not peer_count_gate:
            reasons.append("PEER_COUNT_BELOW_3")
        if not peer_median_complete:
            reasons.append("MISSING_PEER_365_MEDIAN")
        if not cutoff_price_complete:
            reasons.append("MISSING_CUTOFF_PRICE")
        if not feature_cutoff_pass:
            reasons.append("FEATURE_CUTOFF_NOT_ENFORCED")
        if not reasons:
            reasons.append("ELIGIBLE")

        rows.append({
            "tcgplayer_product_id": str(product_id),
            "cutoff_rows": int(len(group)),
            "ages_present": ",".join(map(str, ages)),
            "actual_complete": actual_complete,
            "peer_count_complete": peer_count_complete,
            "minimum_peer_count": peer_count_min,
            "peer_count_gate_pass": peer_count_gate,
            "peer_365_median_complete": peer_median_complete,
            "peer_365_mean_complete": peer_mean_complete,
            "cutoff_price_complete": cutoff_price_complete,
            "feature_cutoff_pass": feature_cutoff_pass,
            "eligible_for_early_tournament": eligible,
            "exclusion_reason": "|".join(reasons),
        })

    adjudication = pd.DataFrame(rows).sort_values(["eligible_for_early_tournament", "tcgplayer_product_id"], ascending=[False, True])

    if not reconciliation.empty:
        rid = first_col(reconciliation, ["tcgplayer_product_id", "product_id"])
        reconciliation[rid] = normalize_id(reconciliation[rid])
        extra_cols = [c for c in ["included_in_early_tournament", "has_peer_maturity_curve", "exclusion_reason"] if c in reconciliation.columns]
        rec = reconciliation[[rid] + extra_cols].drop_duplicates(rid).rename(columns={rid: "tcgplayer_product_id", "exclusion_reason": "prior_reconciliation_reason"})
        adjudication = adjudication.merge(rec, on="tcgplayer_product_id", how="left")

    adjudication.to_csv(OUT_DIR / "collector_v1_early_product_coverage_adjudication.csv", index=False)

    reason_counts = (
        adjudication.assign(reason=adjudication["exclusion_reason"].str.split("|"))
        .explode("reason")
        .groupby("reason", dropna=False)
        .size()
        .reset_index(name="product_count")
        .sort_values(["product_count", "reason"], ascending=[False, True])
    )
    reason_counts.to_csv(OUT_DIR / "collector_v1_early_coverage_reason_counts.csv", index=False)

    eligible_products = int(adjudication["eligible_for_early_tournament"].sum())
    excluded_products = int((~adjudication["eligible_for_early_tournament"]).sum())
    summary = {
        "block_name": "Collector V1 Early Opportunity Coverage Adjudication",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cutoff_rows": int(len(cutoffs)),
        "products_profiled": int(adjudication["tcgplayer_product_id"].nunique()),
        "eligible_products": eligible_products,
        "excluded_products": excluded_products,
        "promotion_scale_required": 30,
        "promotion_scale_reached": eligible_products >= 30,
        "peer_count_column": peer_count_col,
        "peer_median_column": peer_median_col,
        "coverage_adjudication_ready": True,
        "model_promotion_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Use adjudication results to recover valid peer features or approve a governed early-route fallback without lowering thresholds.",
        "status": "PASS_COLLECTOR_V1_EARLY_COVERAGE_ADJUDICATION_READY",
    }
    (OUT_DIR / "collector_v1_early_coverage_adjudication_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
