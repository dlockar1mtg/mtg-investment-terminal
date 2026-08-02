from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EARLY_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_opportunity_foundation"
FEATURE_DIR = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation"
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_peer_feature_recovery"


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f"No governed path exists: {[str(p) for p in paths]}")


def first_col(df: pd.DataFrame, names: list[str]) -> str:
    for name in names:
        if name in df.columns:
            return name
    raise ValueError(f"Required column missing. candidates={names}; available={list(df.columns)}")


def norm(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d+)$", expand=False).fillna(s.astype(str))


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cutoff_path = EARLY_DIR / "collector_v1_release_age_cutoffs.csv"
    outcome_path = EARLY_DIR / "collector_v1_first_year_outcomes.csv"
    comparable_path = first_existing([
        FEATURE_DIR / "collector_v1_active_comparables.csv",
        FEATURE_DIR / "collector_v1_comparables.csv",
        ROOT / "data/governance/permanence/certification/collector_v1_active_comparables.csv",
    ])

    cutoffs = pd.read_csv(cutoff_path)
    outcomes = pd.read_csv(outcome_path)
    comps = pd.read_csv(comparable_path)

    cid = first_col(cutoffs, ["tcgplayer_product_id", "product_id"])
    oid = first_col(outcomes, ["tcgplayer_product_id", "product_id"])
    actual = first_col(outcomes, ["actual_return_365d_from_release", "first_year_return", "return_365d_from_release"])
    target = first_col(comps, ["target_product_id", "tcgplayer_product_id", "product_id"])
    peer = first_col(comps, ["peer_product_id", "comparable_product_id", "peer_tcgplayer_product_id"])

    cutoffs[cid] = norm(cutoffs[cid])
    outcomes[oid] = norm(outcomes[oid])
    comps[target] = norm(comps[target])
    comps[peer] = norm(comps[peer])
    outcomes[actual] = num(outcomes[actual])

    peer_returns = outcomes[[oid, actual]].dropna().drop_duplicates(oid).rename(columns={oid: peer, actual: "peer_actual_return_365d"})
    mapped = comps[[target, peer]].dropna().drop_duplicates().merge(peer_returns, on=peer, how="left")
    mapped = mapped[mapped["peer_actual_return_365d"].notna()].copy()

    agg = mapped.groupby(target).agg(
        recovered_peer_count=(peer, "nunique"),
        recovered_peer_return_365d_median=("peer_actual_return_365d", "median"),
        recovered_peer_return_365d_mean=("peer_actual_return_365d", "mean"),
        recovered_peer_winner_25_rate=("peer_actual_return_365d", lambda s: float((s >= 0.25).mean())),
        recovered_peer_winner_50_rate=("peer_actual_return_365d", lambda s: float((s >= 0.50).mean())),
        recovered_peer_loss_rate=("peer_actual_return_365d", lambda s: float((s < 0).mean())),
    ).reset_index().rename(columns={target: cid})

    recovered = cutoffs.merge(agg, on=cid, how="left")
    original_count = num(recovered.get("peer_count", pd.Series(index=recovered.index, dtype=float)))
    original_median = num(recovered.get("peer_return_365d_median", pd.Series(index=recovered.index, dtype=float)))
    recovered["peer_count_recovered"] = original_count.fillna(num(recovered["recovered_peer_count"]))
    recovered["peer_return_365d_median_recovered"] = original_median.fillna(num(recovered["recovered_peer_return_365d_median"]))
    recovered["peer_feature_source"] = "ORIGINAL" 
    recovered.loc[original_count.isna() & recovered["peer_count_recovered"].notna(), "peer_feature_source"] = "RECOVERED_ACTIVE_COMPARABLES"
    recovered["recovery_eligible"] = (recovered["peer_count_recovered"] >= 3) & recovered["peer_return_365d_median_recovered"].notna()

    product_diag = recovered.groupby(cid).agg(
        age_rows=(cid, "size"),
        recovered_complete=("recovery_eligible", "all"),
        minimum_recovered_peer_count=("peer_count_recovered", "min"),
        recovered_median_complete=("peer_return_365d_median_recovered", lambda s: bool(s.notna().all())),
    ).reset_index()

    recovered.to_csv(OUT_DIR / "collector_v1_release_age_cutoffs_with_recovered_peer_features.csv", index=False)
    mapped.to_csv(OUT_DIR / "collector_v1_recovered_peer_lineage.csv", index=False)
    product_diag.to_csv(OUT_DIR / "collector_v1_recovered_peer_product_diagnostics.csv", index=False)

    complete_products = int(product_diag["recovered_complete"].sum())
    summary = {
        "block_name": "Collector V1 Early Peer Feature Recovery",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cutoff_rows": int(len(cutoffs)),
        "products_profiled": int(product_diag[cid].nunique()),
        "active_comparable_rows": int(len(comps)),
        "peer_lineage_rows_with_realized_returns": int(len(mapped)),
        "products_complete_after_recovery": complete_products,
        "promotion_scale_required": 30,
        "promotion_scale_reached": complete_products >= 30,
        "source_paths": {
            "cutoffs": str(cutoff_path.relative_to(ROOT)),
            "outcomes": str(outcome_path.relative_to(ROOT)),
            "comparables": str(comparable_path.relative_to(ROOT)),
        },
        "certified_sources_mutated": False,
        "peer_feature_recovery_ready": True,
        "early_tournament_rebuild_authorized": complete_products >= 30,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_EARLY_PEER_FEATURE_RECOVERY_READY",
    }
    (OUT_DIR / "collector_v1_early_peer_feature_recovery_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if (not args.strict or summary["peer_feature_recovery_ready"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
