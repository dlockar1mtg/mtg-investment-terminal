from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_peer_set_audit_v1.json"


def trimmed_mean(values: pd.Series, proportion: float = 0.10) -> float | None:
    vals = sorted(pd.to_numeric(values, errors="coerce").dropna().tolist())
    if not vals:
        return None
    trim = int(len(vals) * proportion)
    if trim > 0 and len(vals) > 2 * trim:
        vals = vals[trim:-trim]
    return float(np.mean(vals))


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    recon = ROOT / cfg["inputs"]["reconciliation_root"]
    v2 = ROOT / cfg["inputs"]["candidate_v2_root"]
    out = ROOT / cfg["output_directory"]
    out.mkdir(parents=True, exist_ok=True)

    peer_path = recon / "collector_reconciled_peer_contributions.csv"
    forecast_path = v2 / "collector_candidate_methodology_v2_forecasts.csv"
    missing = [str(p) for p in [peer_path, forecast_path] if not p.exists()]
    if missing:
        result = {"status": "FAIL", "failures": [f"missing_input:{p}" for p in missing]}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    peers = pd.read_csv(peer_path, low_memory=False)
    forecasts = pd.read_csv(forecast_path, low_memory=False)
    for col in ["target_tcgplayer_product_id", "peer_tcgplayer_product_id"]:
        peers[col] = peers[col].astype(str).str.replace(r"\.0$", "", regex=True)
    forecasts["canonical_tcgplayer_product_id"] = forecasts["canonical_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)

    applicable = forecasts[forecasts["forecast_method_route"].isin(["COMPARABLE_PRODUCT_ADJUSTED", "DIRECT_HISTORY_LIMITED"])].copy()
    rows = []
    for _, f in applicable.iterrows():
        pid = str(f["canonical_tcgplayer_product_id"])
        subset = peers[peers["target_tcgplayer_product_id"] == pid].copy()
        subset["peer_return"] = pd.to_numeric(subset.get("peer_annualized_retrospective_return"), errors="coerce")
        subset["score"] = pd.to_numeric(subset.get("similarity_score"), errors="coerce")
        subset = subset.dropna(subset=["peer_return", "score"])
        subset = subset[subset["score"] > 0]
        peer_ids = sorted(subset["peer_tcgplayer_product_id"].astype(str).tolist())
        return_values = sorted(round(float(v), 12) for v in subset["peer_return"].tolist())
        peer_set_hash = hashlib.sha256("|".join(peer_ids).encode("utf-8")).hexdigest()
        return_set_hash = hashlib.sha256("|".join(map(str, return_values)).encode("utf-8")).hexdigest()
        recomputed = trimmed_mean(subset["peer_return"])
        stored = pd.to_numeric(pd.Series([f.get("variant_peer_trimmed_mean_10_percent")]), errors="coerce").iloc[0]
        stored = None if pd.isna(stored) else float(stored)
        delta = None if recomputed is None or stored is None else recomputed - stored
        rows.append({
            "canonical_tcgplayer_product_id": pid,
            "product_name": f.get("product_name", ""),
            "forecast_method_route": f.get("forecast_method_route", ""),
            "peer_count": int(len(subset)),
            "unique_peer_count": int(subset["peer_tcgplayer_product_id"].nunique()),
            "peer_set_sha256": peer_set_hash,
            "peer_return_set_sha256": return_set_hash,
            "recomputed_trimmed_mean_10_percent": recomputed,
            "stored_trimmed_mean_10_percent": stored,
            "trimmed_mean_delta": delta,
            "trimmed_mean_matches": bool(delta is not None and abs(delta) <= 1e-12),
            "target_specific_peer_rows_present": bool(len(subset) > 0),
        })

    detail = pd.DataFrame(rows)
    detail.to_csv(out / "collector_candidate_v2_peer_set_detail.csv", index=False)
    groups = detail.groupby(["peer_set_sha256", "peer_return_set_sha256"], dropna=False).agg(
        target_count=("canonical_tcgplayer_product_id", "count"),
        product_examples=("product_name", lambda s: " | ".join(list(s)[:5])),
        peer_count=("peer_count", "first"),
        trimmed_mean=("recomputed_trimmed_mean_10_percent", "first"),
    ).reset_index()
    groups.to_csv(out / "collector_candidate_v2_peer_set_groups.csv", index=False)

    target_count = int(len(detail))
    unique_peer_sets = int(detail["peer_set_sha256"].nunique())
    unique_return_sets = int(detail["peer_return_set_sha256"].nunique())
    unique_trimmed = int(detail["recomputed_trimmed_mean_10_percent"].round(12).nunique())
    matching_count = int(detail["trimmed_mean_matches"].map(truthy).sum())
    global_pool_collapse = bool(target_count > 1 and unique_peer_sets == 1)
    summary = {
        "audit_name": "Collector Candidate v2 Peer-Set Diversity Audit",
        "audit_version": "1.0.0",
        "status": "PASS",
        "target_count": target_count,
        "unique_peer_set_count": unique_peer_sets,
        "unique_peer_return_set_count": unique_return_sets,
        "unique_recomputed_trimmed_mean_count": unique_trimmed,
        "stored_recomputed_match_count": matching_count,
        "global_pool_collapse_detected": global_pool_collapse,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": 0,
        "failures": [],
    }
    if target_count != 31:
        summary["failures"].append("unexpected_applicable_target_count")
    if matching_count != target_count:
        summary["failures"].append("stored_trimmed_means_do_not_match_target_recomputation")
    if global_pool_collapse:
        summary["failures"].append("all_targets_share_one_peer_set")
    if unique_peer_sets < 2:
        summary["failures"].append("insufficient_peer_set_diversity")
    summary["failure_count"] = len(summary["failures"])
    if summary["failure_count"]:
        summary["status"] = "FAIL"
    (out / "collector_candidate_v2_peer_set_audit_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
