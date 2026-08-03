from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_methodology_v2/candidate_v2_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    files = {
        "forecasts": OUT / "collector_candidate_methodology_v2_forecasts.csv",
        "comparison": OUT / "collector_candidate_methodology_v2_comparison.csv",
        "routes": OUT / "collector_candidate_methodology_v2_route_summary.csv",
        "approvals": OUT / "collector_candidate_methodology_v2_owner_approval_register.csv",
        "summary": OUT / "collector_candidate_methodology_v2_summary.json",
    }
    failures = [f"missing_{k}:{v}" for k, v in files.items() if not v.exists()]
    if failures:
        result = {"status": "FAIL", "failures": failures, "failure_count": len(failures)}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    forecasts = pd.read_csv(files["forecasts"], low_memory=False)
    approvals = pd.read_csv(files["approvals"], low_memory=False)
    summary = json.loads(files["summary"].read_text(encoding="utf-8"))

    checks = {
        "product_count": len(forecasts) == 51,
        "unique_products": forecasts["canonical_tcgplayer_product_id"].nunique() == 51,
        "route_count": forecasts["forecast_method_route"].nunique() == 4,
        "owner_decision_count": len(approvals) == 6,
        "reverse_score_diagnostic_only_count": int((forecasts["candidate_v2_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum()) == 7,
        "japanese_hybrid_inactive_count": int((forecasts["candidate_v2_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum()) == 1,
        "trimmed_peer_method_present": int((forecasts["candidate_v2_peer_aggregation"] == "PEER_TRIMMED_MEAN_10_PERCENT").sum()) == 31,
        "short_history_method_count": int((forecasts["candidate_v2_short_history_treatment"] == "SIMPLE_RETURN_UNTIL_365_DAYS_OBSERVED").sum()) == 7,
        "candidate_projection_authorized_false": not forecasts["candidate_projection_authorized"].map(truthy).any(),
        "production_projection_authorized_false": not forecasts["production_projection_authorized"].map(truthy).any(),
        "purchase_recommendation_authorized_false": not forecasts["purchase_recommendation_authorized"].map(truthy).any(),
        "automatic_model_update_allowed_false": not forecasts["automatic_model_update_allowed"].map(truthy).any(),
        "approval_activation_false": not approvals["activation_authorized"].map(truthy).any(),
        "summary_pass": summary.get("status") == "PASS",
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "audit_name": "Collector Candidate Methodology v2 Audit",
        "audit_version": "2.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(forecasts)),
        "candidate_v2_complete_count": int(forecasts["candidate_v2_calculation_complete"].map(truthy).sum()),
        "reverse_score_diagnostic_only_count": int((forecasts["candidate_v2_method_status"] == "DIAGNOSTIC_ONLY_REVERSE_SCORE_NOT_PRODUCTION_ELIGIBLE").sum()),
        "japanese_hybrid_inactive_count": int((forecasts["candidate_v2_method_status"] == "FORMULA_INACTIVE_OWNER_DECISION").sum()),
        "owner_decision_count": int(len(approvals)),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit validates candidate methodology v2 development outputs only. It does not authorize production forecasts, purchases, automatic updates, reverse-score production use, or the Japanese hybrid formula.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
