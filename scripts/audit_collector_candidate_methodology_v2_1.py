from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_methodology_v2_1/candidate_v2_1_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "forecasts": OUT / "collector_candidate_methodology_v2_1_forecasts.csv",
        "lineage": OUT / "collector_candidate_methodology_v2_1_peer_lineage.csv",
        "summary": OUT / "collector_candidate_methodology_v2_1_summary.json",
    }
    failures = [f"missing_output:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)
    lineage = pd.read_csv(paths["lineage"], low_memory=False)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))

    checks = []
    if len(forecasts) != 51:
        checks.append("product_count_not_51")
    if int(forecasts["candidate_v2_1_calculation_complete"].map(truthy).sum()) != 50:
        checks.append("complete_count_not_50")
    if int((forecasts["candidate_v2_1_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum()) != 1:
        checks.append("japanese_hybrid_inactive_count_not_1")
    if int((forecasts["candidate_v2_1_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum()) != 7:
        checks.append("reverse_score_diagnostic_count_not_7")
    if len(lineage) != 31:
        checks.append("peer_lineage_target_count_not_31")
    if not lineage["route_blend_applied_once"].map(truthy).all():
        checks.append("route_blend_not_applied_exactly_once")
    limited = forecasts[forecasts["forecast_method_route"] == "DIRECT_HISTORY_LIMITED"]
    if limited["candidate_v2_1_simple_history_return"].isna().any():
        checks.append("limited_simple_history_missing")
    if forecasts["candidate_projection_authorized"].map(truthy).any():
        checks.append("candidate_projection_authorized")
    if forecasts["production_projection_authorized"].map(truthy).any():
        checks.append("production_projection_authorized")
    if forecasts["purchase_recommendation_authorized"].map(truthy).any():
        checks.append("purchase_recommendation_authorized")

    result = {
        "audit_name": "Collector Candidate Methodology v2.1 Audit",
        "audit_version": "2.1.0",
        "status": "PASS" if not checks else "FAIL",
        "product_count": int(len(forecasts)),
        "complete_count": int(forecasts["candidate_v2_1_calculation_complete"].map(truthy).sum()),
        "peer_lineage_target_count": int(len(lineage)),
        "comparable_unweighted_trimmed_unique_value_count": int(summary.get("comparable_unweighted_trimmed_unique_value_count", 0)),
        "comparable_similarity_weighted_trimmed_unique_value_count": int(summary.get("comparable_similarity_weighted_trimmed_unique_value_count", 0)),
        "failure_count": len(checks),
        "failures": checks,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This audit validates v2.1 component lineage and one-time route blending. It does not approve the similarity-weighted amendment diagnostic or authorize production or purchases."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
