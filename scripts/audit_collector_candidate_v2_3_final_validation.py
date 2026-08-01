from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_3_final_validation_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    out = ROOT / cfg["output_directory"]
    summary_path = out / "collector_candidate_v2_3_final_validation_summary.json"
    recommendation_path = out / "collector_candidate_v2_3_freeze_recommendation.json"
    hashes_path = out / "collector_candidate_v2_3_artifact_hash_manifest.csv"
    routes_path = out / "collector_candidate_v2_3_final_route_validation.csv"
    exceptions_path = out / "collector_candidate_v2_3_exception_register.csv"
    required = [summary_path, recommendation_path, hashes_path, routes_path, exceptions_path]
    missing = [str(path) for path in required if not path.exists()]
    failures: list[str] = [f"missing_output:{path}" for path in missing]

    summary = {}
    recommendation = {}
    hashes = pd.DataFrame()
    routes = pd.DataFrame()
    exceptions = pd.DataFrame()
    if not missing:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
        hashes = pd.read_csv(hashes_path, low_memory=False)
        routes = pd.read_csv(routes_path, low_memory=False)
        exceptions = pd.read_csv(exceptions_path, low_memory=False)

        if summary.get("status") != "PASS":
            failures.append("summary_not_pass")
        if summary.get("freeze_recommendation") != "TECHNICAL_FREEZE_RECOMMENDED_WITH_EXCLUSIONS":
            failures.append("freeze_recommendation_not_expected")
        if int(summary.get("product_count", 0)) != 51:
            failures.append("product_count_mismatch")
        if int(summary.get("complete_count", 0)) != 50:
            failures.append("complete_count_mismatch")
        if int(summary.get("route_count", 0)) != 4 or len(routes) != 4:
            failures.append("route_count_mismatch")
        if int(summary.get("reverse_score_diagnostic_only_count", 0)) != 7:
            failures.append("reverse_score_count_mismatch")
        if int(summary.get("japanese_hybrid_inactive_count", 0)) != 1:
            failures.append("hybrid_inactive_count_mismatch")
        if len(hashes) != 5 or hashes["sha256"].astype(str).str.len().ne(64).any():
            failures.append("artifact_hash_manifest_invalid")
        required_exclusions = set(cfg["freeze_policy"]["required_exclusions"])
        actual_exclusions = set(recommendation.get("documented_exclusions", []))
        if required_exclusions != actual_exclusions:
            failures.append("documented_exclusions_mismatch")
        restricted = [
            "production_projection_authorized",
            "purchase_recommendation_authorized",
            "automatic_model_update_allowed",
            "reverse_score_production_use_authorized",
            "japanese_hybrid_formula_authorized",
        ]
        for key in restricted:
            if truthy(recommendation.get(key)):
                failures.append(f"authorization_open:{key}")
        if truthy(recommendation.get("prospective_accuracy_certified")):
            failures.append("prospective_accuracy_incorrectly_certified")
        if not truthy(recommendation.get("owner_freeze_approval_required")):
            failures.append("owner_freeze_approval_not_required")
        if exceptions.empty:
            failures.append("exception_register_empty")
        else:
            reasons = "|".join(exceptions["exception_reasons"].fillna("").astype(str).tolist())
            if "REVERSE_SCORE_ROUTE_NOT_PRODUCTION_ELIGIBLE" not in reasons:
                failures.append("reverse_score_exception_missing")
            if "JAPANESE_HYBRID_FORMULA_INACTIVE" not in reasons:
                failures.append("hybrid_exception_missing")
            if exceptions["production_eligible"].map(truthy).any():
                failures.append("exception_marked_production_eligible")

    result = {
        "audit_name": "Collector Candidate v2.3 Final Validation Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "freeze_recommendation": summary.get("freeze_recommendation"),
        "product_count": summary.get("product_count"),
        "complete_count": summary.get("complete_count"),
        "route_count": summary.get("route_count"),
        "exception_product_count": 0 if exceptions.empty else int(len(exceptions)),
        "artifact_hash_count": 0 if hashes.empty else int(len(hashes)),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "owner_freeze_approval_required": True,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit validates the technical freeze recommendation and its exclusions. It does not freeze the candidate by itself or authorize production forecasts or purchases.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
