from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "config/mtg/governance/collector_candidate_methodology_v2_2_approval.json"
RECON = ROOT / "data/operations/collector_route_reconciliation/candidate_v1_0_0"
EVIDENCE = ROOT / "data/operations/collector_methodology_evidence_review/candidate_v1_0_0"
V21 = ROOT / "data/operations/collector_candidate_methodology_v2_1/candidate_v2_1_0"
OUT = ROOT / "data/operations/collector_candidate_methodology_v2_2/candidate_v2_2_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def trimmed_weighted(frame: pd.DataFrame, proportion: float = 0.10) -> tuple[float | None, int, int]:
    work = frame.copy()
    work["peer_return"] = pd.to_numeric(work["peer_annualized_retrospective_return"], errors="coerce")
    work["score"] = pd.to_numeric(work["similarity_score"], errors="coerce")
    work = work.dropna(subset=["peer_return", "score"])
    work = work[work["score"] > 0].sort_values("peer_return").reset_index(drop=True)
    before = int(len(work))
    trim = int(before * proportion)
    if trim > 0 and before > trim * 2:
        work = work.iloc[trim:-trim].copy()
    after = int(len(work))
    if work.empty:
        return None, before, after
    return float(np.average(work["peer_return"], weights=work["score"])), before, after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "approval": APPROVAL,
        "forecasts": RECON / "collector_reconciled_candidate_forecasts.csv",
        "peers": RECON / "collector_reconciled_peer_contributions.csv",
        "outcomes": EVIDENCE / "collector_retrospective_outcome_diagnostics.csv",
        "v21": V21 / "collector_candidate_methodology_v2_1_forecasts.csv",
    }
    missing = [f"missing_input:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if missing:
        result = {"status": "FAIL", "failure_count": len(missing), "failures": missing}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)
    peers = pd.read_csv(paths["peers"], low_memory=False)
    outcomes = pd.read_csv(paths["outcomes"], low_memory=False)
    v21 = pd.read_csv(paths["v21"], low_memory=False)

    pid = "canonical_tcgplayer_product_id"
    for frame in (forecasts, outcomes, v21):
        frame[pid] = frame[pid].astype(str).str.replace(r"\.0$", "", regex=True)
    peers["target_tcgplayer_product_id"] = peers["target_tcgplayer_product_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    outcome_map = outcomes.set_index(pid).to_dict("index")
    v21_map = v21.set_index(pid).to_dict("index")

    rows: list[dict[str, object]] = []
    lineage_rows: list[dict[str, object]] = []
    for _, row in forecasts.iterrows():
        target = str(row[pid])
        route = str(row.get("forecast_method_route", ""))
        baseline = num(row.get("base_annual_rate"))
        fundamental = num(row.get("fundamental_adjustment_annual_rate")) or 0.0
        simple_history = num(outcome_map.get(target, {}).get("simple_return"))
        peer_rate, before, after = trimmed_weighted(peers[peers["target_tcgplayer_product_id"] == target])

        status = "APPROVED_CANDIDATE_V2_2"
        candidate = baseline
        if route == "COMPARABLE_PRODUCT_ADJUSTED":
            candidate = None if peer_rate is None else peer_rate + fundamental
        elif route == "DIRECT_HISTORY_LIMITED":
            if truthy(row.get("reverse_pair_candidate_used")):
                status = "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE"
            candidate = None if simple_history is None or peer_rate is None else (0.25 * simple_history) + (0.75 * peer_rate) + fundamental
        elif route == "FUNDAMENTAL_COMPARABLE_HYBRID":
            status = "FORMULA_INACTIVE_OWNER_DECISION"
            candidate = None

        v21_rate = num(v21_map.get(target, {}).get("candidate_v2_1_base_annual_rate"))
        width = num(row.get("uncertainty_width"))
        downside = None if candidate is None or width is None else candidate - width
        upside = None if candidate is None or width is None else candidate + width
        extreme = bool(candidate is not None and abs(candidate) >= 1.0)

        out = row.to_dict()
        out.update({
            "candidate_methodology_version": "2.2.0",
            "candidate_v2_2_peer_trimmed_mean_similarity_weighted": peer_rate,
            "candidate_v2_2_simple_history_return": simple_history,
            "candidate_v2_2_base_annual_rate": candidate,
            "candidate_v2_2_downside_annual_rate": downside,
            "candidate_v2_2_upside_annual_rate": upside,
            "baseline_to_v2_2_change": None if candidate is None or baseline is None else candidate - baseline,
            "v2_1_to_v2_2_change": None if candidate is None or v21_rate is None else candidate - v21_rate,
            "candidate_v2_2_method_status": status,
            "candidate_v2_2_calculation_complete": candidate is not None,
            "extreme_rate_review_required": extreme,
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
                "peer_count_before_trim": before,
                "peer_count_after_trim": after,
                "peer_trimmed_mean_similarity_weighted": peer_rate,
                "simple_history_return": simple_history,
                "fundamental_adjustment_annual_rate": fundamental,
                "route_blend_applied_once": True,
                "reverse_score_diagnostic_only": truthy(row.get("reverse_pair_candidate_used")),
            })

    result = pd.DataFrame(rows)
    lineage = pd.DataFrame(lineage_rows)
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / "collector_candidate_methodology_v2_2_forecasts.csv", index=False)
    lineage.to_csv(OUT / "collector_candidate_methodology_v2_2_peer_lineage.csv", index=False)

    comparison = result[[pid, "product_name", "forecast_method_route", "base_annual_rate", "candidate_v2_2_base_annual_rate", "baseline_to_v2_2_change", "v2_1_to_v2_2_change", "candidate_v2_2_method_status", "extreme_rate_review_required", "candidate_v2_2_calculation_complete"]].copy()
    comparison.to_csv(OUT / "collector_candidate_methodology_v2_2_comparison.csv", index=False)

    route_summary = result.groupby("forecast_method_route", dropna=False).agg(
        product_count=(pid, "count"),
        complete_count=("candidate_v2_2_calculation_complete", lambda s: int(s.map(truthy).sum())),
        mean_baseline_rate=("base_annual_rate", "mean"),
        mean_candidate_v2_2_rate=("candidate_v2_2_base_annual_rate", "mean"),
        mean_baseline_to_v2_2_change=("baseline_to_v2_2_change", "mean"),
        mean_v2_1_to_v2_2_change=("v2_1_to_v2_2_change", "mean"),
        extreme_rate_review_count=("extreme_rate_review_required", lambda s: int(s.map(truthy).sum())),
    ).reset_index()
    route_summary.to_csv(OUT / "collector_candidate_methodology_v2_2_route_summary.csv", index=False)

    approval_register = pd.DataFrame([
        {"decision_id": "COL-METH-003", "owner_decision": approval["owner_decision"]["decision"], "approval_scope": approval["scope"], "supersedes": approval["supersedes"]["prior_decision"], "activation_authorized": False},
        *[
            {"decision_id": k, "owner_decision": v, "approval_scope": approval["scope"], "supersedes": "", "activation_authorized": False}
            for k, v in approval["preserved_decisions"].items()
        ],
    ])
    approval_register.to_csv(OUT / "collector_candidate_methodology_v2_2_owner_approval_register.csv", index=False)

    complete = int(result["candidate_v2_2_calculation_complete"].map(truthy).sum())
    inactive = int((result["candidate_v2_2_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum())
    reverse = int((result["candidate_v2_2_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum())
    comp_unique = int(lineage[lineage["forecast_method_route"] == "COMPARABLE_PRODUCT_ADJUSTED"]["peer_trimmed_mean_similarity_weighted"].round(12).nunique())
    limited_unique = int(lineage[lineage["forecast_method_route"] == "DIRECT_HISTORY_LIMITED"]["peer_trimmed_mean_similarity_weighted"].round(12).nunique())
    summary = {
        "audit_name": "Collector Candidate Methodology v2.2",
        "audit_version": "2.2.0",
        "status": "PASS",
        "product_count": int(len(result)),
        "complete_count": complete,
        "incomplete_count": int(len(result) - complete),
        "japanese_hybrid_inactive_count": inactive,
        "reverse_score_diagnostic_only_count": reverse,
        "peer_lineage_target_count": int(len(lineage)),
        "comparable_similarity_weighted_trimmed_unique_value_count": comp_unique,
        "limited_similarity_weighted_trimmed_unique_value_count": limited_unique,
        "owner_decision_count": int(len(approval_register)),
        "candidate_development_authorized": True,
        "candidate_testing_authorized": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "governing_note": "Candidate v2.2 implements the owner-approved similarity-weighted 10% trimmed peer mean for development and testing only. Reverse-score routes remain diagnostic only and the Japanese hybrid formula remains inactive.",
        "failure_count": 0,
        "failures": [],
    }
    if len(result) != 51 or complete != 50 or inactive != 1 or reverse != 7 or len(lineage) != 31 or len(approval_register) != 6 or comp_unique < 2 or limited_unique != 7:
        summary["status"] = "FAIL"
        summary["failures"] = ["structural_or_target_specificity_expectation_failed"]
        summary["failure_count"] = 1
    (OUT / "collector_candidate_methodology_v2_2_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
