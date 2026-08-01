from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_2_scenario_confidence_review/candidate_v1_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    paths = {
        "product": OUT / "collector_candidate_v2_2_scenario_confidence_product_review.csv",
        "variants": OUT / "collector_candidate_v2_2_scenario_width_variants.csv",
        "route": OUT / "collector_candidate_v2_2_scenario_confidence_route_summary.csv",
        "queue": OUT / "collector_candidate_v2_2_scenario_confidence_review_queue.csv",
        "summary": OUT / "collector_candidate_v2_2_scenario_confidence_review_summary.json",
    }
    failures = [f"missing_output:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    product = pd.read_csv(paths["product"], low_memory=False)
    variants = pd.read_csv(paths["variants"], low_memory=False)
    route = pd.read_csv(paths["route"], low_memory=False)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    pid = "canonical_tcgplayer_product_id"
    checks = []
    checks.append((len(product) == 51, "product_count_not_51"))
    checks.append((product[pid].astype(str).nunique() == 51, "product_ids_not_unique"))
    checks.append((len(variants) == 255, "variant_row_count_not_255"))
    checks.append((variants.groupby(pid).size().eq(5).all(), "variant_count_not_5_per_product"))
    checks.append((len(route) == 4, "route_count_not_4"))
    checks.append((int(product["candidate_v2_2_calculation_complete"].map(truthy).sum()) == 50, "complete_count_not_50"))
    checks.append((product["scenario_methodology_authorized"].map(truthy).sum() == 0, "scenario_authorization_open"))
    checks.append((product["confidence_methodology_authorized"].map(truthy).sum() == 0, "confidence_authorization_open"))
    checks.append((product["production_projection_authorized"].map(truthy).sum() == 0, "production_authorization_open"))
    checks.append((product["purchase_recommendation_authorized"].map(truthy).sum() == 0, "purchase_authorization_open"))
    checks.append((product["automatic_model_update_allowed"].map(truthy).sum() == 0, "automatic_update_open"))
    checks.append((summary.get("status") == "PASS", "builder_summary_not_pass"))
    failures.extend(message for passed, message in checks if not passed)
    result = {
        "audit_name": "Collector Candidate v2.2 Scenario and Confidence Review Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(product)),
        "variant_row_count": int(len(variants)),
        "route_count": int(len(route)),
        "scenario_width_review_count": int(product["scenario_width_review_required"].map(truthy).sum()),
        "confidence_review_count": int(product["confidence_review_required"].map(truthy).sum()),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This audit verifies diagnostic scenario and confidence review outputs and closed authorization boundaries. It does not approve a replacement scenario or confidence methodology.",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
