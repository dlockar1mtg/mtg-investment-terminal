from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_methodology_v2_1_lineage_repair.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def trimmed_frame(frame: pd.DataFrame, proportion: float = 0.10) -> pd.DataFrame:
    work = frame.copy()
    work["peer_return"] = pd.to_numeric(work["peer_annualized_retrospective_return"], errors="coerce")
    work["score"] = pd.to_numeric(work["similarity_score"], errors="coerce")
    work = work.dropna(subset=["peer_return", "score"])
    work = work[work["score"] > 0].sort_values("peer_return").reset_index(drop=True)
    trim = int(len(work) * proportion)
    if trim > 0 and len(work) > trim * 2:
        work = work.iloc[trim:-trim].copy()
    return work


def unweighted_mean(frame: pd.DataFrame) -> float | None:
    return None if frame.empty else float(frame["peer_return"].mean())


def weighted_mean(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    return float(np.average(frame["peer_return"], weights=frame["score"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    recon = ROOT / cfg["inputs"]["reconciliation_root"]
    out_dir = ROOT / cfg["output_directory"]
    paths = {
        "approval": ROOT / cfg["inputs"]["approval"],
        "forecasts": recon / "collector_reconciled_candidate_forecasts.csv",
        "peers": recon / "collector_reconciled_peer_contributions.csv",
    }
    missing = [f"missing_input:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if missing:
        result = {"status": "FAIL", "failure_count": len(missing), "failures": missing}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    approval = json.loads(paths["approval"].read_text(encoding="utf-8"))
    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)
    peers = pd.read_csv(paths["peers"], low_memory=False)
    pid = "canonical_tcgplayer_product_id"
    forecasts[pid] = forecasts[pid].astype(str).str.replace(r"\.0$", "", regex=True)
    peers["target_tcgplayer_product_id"] = peers["target_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)

    rows = []
    lineage_rows = []
    for _, row in forecasts.iterrows():
        out = row.to_dict()
        target = str(row[pid])
        route = str(row.get("forecast_method_route", ""))
        baseline = num(row.get("base_annual_rate"))
        fundamental = num(row.get("fundamental_adjustment_annual_rate")) or 0.0
        simple_history = num(row.get("retrospective_simple_return"))
        if simple_history is None:
            simple_history = num(row.get("variant_short_history_simple_return"))
        target_peers = peers[peers["target_tcgplayer_product_id"] == target].copy()
        trimmed = trimmed_frame(target_peers)
        peer_unweighted = unweighted_mean(trimmed)
        peer_weighted = weighted_mean(trimmed)

        status = "APPROVED_CANDIDATE_V2_1"
        candidate = baseline
        if route == "COMPARABLE_PRODUCT_ADJUSTED":
            candidate = None if peer_unweighted is None else peer_unweighted + fundamental
        elif route == "DIRECT_HISTORY_LIMITED":
            if truthy(row.get("reverse_pair_candidate_used")):
                status = "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE"
            candidate = None if simple_history is None or peer_unweighted is None else 0.25 * simple_history + 0.75 * peer_unweighted + fundamental
        elif route == "FUNDAMENTAL_COMPARABLE_HYBRID":
            status = "FORMULA_INACTIVE_OWNER_DECISION"
            candidate = None

        weighted_amendment = None
        if route == "COMPARABLE_PRODUCT_ADJUSTED" and peer_weighted is not None:
            weighted_amendment = peer_weighted + fundamental
        elif route == "DIRECT_HISTORY_LIMITED" and simple_history is not None and peer_weighted is not None:
            weighted_amendment = 0.25 * simple_history + 0.75 * peer_weighted + fundamental

        out.update({
            "candidate_methodology_version": "2.1.0",
            "candidate_v2_1_peer_trimmed_mean_unweighted": peer_unweighted,
            "candidate_v2_1_peer_trimmed_mean_similarity_weighted_diagnostic": peer_weighted,
            "candidate_v2_1_base_annual_rate": candidate,
            "candidate_v2_1_weighted_trimmed_amendment_diagnostic_rate": weighted_amendment,
            "candidate_v2_1_weighted_trimmed_minus_unweighted": None if candidate is None or weighted_amendment is None else weighted_amendment - candidate,
            "candidate_v2_1_method_status": status,
            "candidate_v2_1_calculation_complete": candidate is not None,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "automatic_model_update_allowed": False,
        })
        rows.append(out)
        if route in {"COMPARABLE_PRODUCT_ADJUSTED", "DIRECT_HISTORY_LIMITED"}:
            lineage_rows.append({
                pid: target,
                "product_name": row.get("product_name", ""),
                "forecast_method_route": route,
                "peer_count_before_trim": int(len(target_peers)),
                "peer_count_after_trim": int(len(trimmed)),
                "peer_trimmed_mean_unweighted": peer_unweighted,
                "peer_trimmed_mean_similarity_weighted_diagnostic": peer_weighted,
                "route_blend_applied_once": True,
                "reverse_score_diagnostic_only": truthy(row.get("reverse_pair_candidate_used")),
            })

    result = pd.DataFrame(rows)
    lineage = pd.DataFrame(lineage_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "collector_candidate_methodology_v2_1_forecasts.csv", index=False)
    lineage.to_csv(out_dir / "collector_candidate_methodology_v2_1_peer_lineage.csv", index=False)

    comparison = result[[pid, "product_name", "forecast_method_route", "base_annual_rate", "candidate_v2_1_base_annual_rate", "candidate_v2_1_weighted_trimmed_amendment_diagnostic_rate", "candidate_v2_1_weighted_trimmed_minus_unweighted", "candidate_v2_1_method_status", "candidate_v2_1_calculation_complete"]].copy()
    comparison.to_csv(out_dir / "collector_candidate_methodology_v2_1_comparison.csv", index=False)

    complete = int(result["candidate_v2_1_calculation_complete"].map(truthy).sum())
    inactive = int((result["candidate_v2_1_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum())
    reverse = int((result["candidate_v2_1_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum())
    comparable_unique = int(lineage[lineage["forecast_method_route"] == "COMPARABLE_PRODUCT_ADJUSTED"]["peer_trimmed_mean_unweighted"].round(12).nunique())
    weighted_unique = int(lineage[lineage["forecast_method_route"] == "COMPARABLE_PRODUCT_ADJUSTED"]["peer_trimmed_mean_similarity_weighted_diagnostic"].round(12).nunique())
    summary = {
        "audit_name": "Collector Candidate Methodology v2.1 Lineage Repair",
        "audit_version": "2.1.0",
        "status": "PASS",
        "product_count": int(len(result)),
        "complete_count": complete,
        "incomplete_count": int(len(result) - complete),
        "japanese_hybrid_inactive_count": inactive,
        "reverse_score_diagnostic_only_count": reverse,
        "peer_lineage_target_count": int(len(lineage)),
        "comparable_unweighted_trimmed_unique_value_count": comparable_unique,
        "comparable_similarity_weighted_trimmed_unique_value_count": weighted_unique,
        "candidate_development_authorized": bool(approval["authorization_boundaries"]["candidate_development_authorized"]),
        "candidate_testing_authorized": bool(approval["authorization_boundaries"]["candidate_testing_authorized"]),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "v2.1 repairs peer-component lineage and prevents double blending. The owner-approved unweighted 10% trimmed mean remains the active candidate calculation; similarity-weighted trimmed results are amendment diagnostics only.",
        "failure_count": 0,
        "failures": [],
    }
    if len(result) != 51 or complete != 50 or inactive != 1 or reverse != 7 or len(lineage) != 31:
        summary["status"] = "FAIL"
        summary["failures"] = ["structural_expectation_failed"]
        summary["failure_count"] = 1
    (out_dir / "collector_candidate_methodology_v2_1_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
