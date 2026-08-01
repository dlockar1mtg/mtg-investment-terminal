from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_2_economic_review/candidate_v1_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "product": OUT / "collector_candidate_v2_2_economic_product_review.csv",
        "route": OUT / "collector_candidate_v2_2_economic_route_summary.csv",
        "queue": OUT / "collector_candidate_v2_2_economic_review_queue.csv",
        "summary": OUT / "collector_candidate_v2_2_economic_review_summary.json",
    }
    failures = [f"missing_output:{k}:{v}" for k, v in paths.items() if not v.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    product = pd.read_csv(paths["product"], low_memory=False)
    route = pd.read_csv(paths["route"], low_memory=False)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))

    checks = []
    checks.append((len(product) == 51, "product_count_not_51"))
    checks.append((product["canonical_tcgplayer_product_id"].astype(str).nunique() == 51, "duplicate_product_ids"))
    checks.append((int(product["candidate_v2_2_calculation_complete"].map(truthy).sum()) == 50, "complete_count_not_50"))
    checks.append((product["forecast_method_route"].nunique() == 4, "route_count_not_4"))
    checks.append((len(route) == 4, "route_summary_count_not_4"))
    checks.append((int(product["reverse_score_review_required"].map(truthy).sum()) == 7, "reverse_score_review_count_not_7"))
    checks.append((int(product["inactive_formula_review_required"].map(truthy).sum()) == 1, "inactive_formula_review_count_not_1"))
    checks.append((not product["candidate_projection_authorized"].map(truthy).any(), "candidate_projection_authorized"))
    checks.append((not product["production_projection_authorized"].map(truthy).any(), "production_projection_authorized"))
    checks.append((not product["purchase_recommendation_authorized"].map(truthy).any(), "purchase_recommendation_authorized"))
    checks.append((not product["automatic_model_update_allowed"].map(truthy).any(), "automatic_model_update_allowed"))

    failures = [name for passed, name in checks if not passed]
    result = {
        "audit_name": "Collector Candidate v2.2 Economic Reasonableness Review Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(product)),
        "complete_count": int(product["candidate_v2_2_calculation_complete"].map(truthy).sum()),
        "route_count": int(product["forecast_method_route"].nunique()),
        "economic_review_required_count": int(product["economic_review_required"].map(truthy).sum()),
        "reverse_score_review_count": int(product["reverse_score_review_required"].map(truthy).sum()),
        "inactive_formula_review_count": int(product["inactive_formula_review_required"].map(truthy).sum()),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "governing_note": "This audit verifies economic-review outputs and closed authorization boundaries. It does not certify forecast accuracy or authorize production or purchases.",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
