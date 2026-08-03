from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_methodology_v2_2/candidate_v2_2_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "forecasts": OUT / "collector_candidate_methodology_v2_2_forecasts.csv",
        "lineage": OUT / "collector_candidate_methodology_v2_2_peer_lineage.csv",
        "comparison": OUT / "collector_candidate_methodology_v2_2_comparison.csv",
        "routes": OUT / "collector_candidate_methodology_v2_2_route_summary.csv",
        "approval": OUT / "collector_candidate_methodology_v2_2_owner_approval_register.csv",
        "summary": OUT / "collector_candidate_methodology_v2_2_summary.json",
    }
    failures = [f"missing_output:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(paths["forecasts"], low_memory=False)
    lineage = pd.read_csv(paths["lineage"], low_memory=False)
    approval = pd.read_csv(paths["approval"], low_memory=False)

    complete = int(forecasts["candidate_v2_2_calculation_complete"].map(truthy).sum())
    inactive = int((forecasts["candidate_v2_2_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum())
    reverse = int((forecasts["candidate_v2_2_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum())
    comp_unique = int(lineage[lineage["forecast_method_route"] == "COMPARABLE_PRODUCT_ADJUSTED"]["peer_trimmed_mean_similarity_weighted"].round(12).nunique())
    limited_unique = int(lineage[lineage["forecast_method_route"] == "DIRECT_HISTORY_LIMITED"]["peer_trimmed_mean_similarity_weighted"].round(12).nunique())

    checks = {
        "product_count": len(forecasts) == 51,
        "complete_count": complete == 50,
        "japanese_inactive": inactive == 1,
        "reverse_diagnostic_only": reverse == 7,
        "peer_lineage_count": len(lineage) == 31,
        "approval_count": len(approval) == 6,
        "route_blend_once": lineage["route_blend_applied_once"].map(truthy).all(),
        "target_specific_comparable_values": comp_unique >= 2,
        "target_specific_limited_values": limited_unique == 7,
        "no_activation": (~approval["activation_authorized"].map(truthy)).all(),
        "no_candidate_projection": (~forecasts["candidate_projection_authorized"].map(truthy)).all(),
        "no_production_projection": (~forecasts["production_projection_authorized"].map(truthy)).all(),
        "no_purchase_authorization": (~forecasts["purchase_recommendation_authorized"].map(truthy)).all(),
        "no_automatic_update": (~forecasts["automatic_model_update_allowed"].map(truthy)).all(),
    }
    failed = [name for name, passed in checks.items() if not bool(passed)]
    result = {
        "audit_name": "Collector Candidate Methodology v2.2 Audit",
        "audit_version": "2.2.0",
        "status": "PASS" if not failed else "FAIL",
        "product_count": int(len(forecasts)),
        "complete_count": complete,
        "japanese_hybrid_inactive_count": inactive,
        "reverse_score_diagnostic_only_count": reverse,
        "peer_lineage_target_count": int(len(lineage)),
        "comparable_similarity_weighted_trimmed_unique_value_count": comp_unique,
        "limited_similarity_weighted_trimmed_unique_value_count": limited_unique,
        "owner_decision_count": int(len(approval)),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This audit validates Candidate v2.2 development outputs, target-specific similarity-weighted trimming, one-time route blending, and closed authorization boundaries. It does not authorize production forecasts or purchases.",
        "failure_count": len(failed),
        "failures": failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
