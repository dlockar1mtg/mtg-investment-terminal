from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_methodology_sensitivity_review/candidate_v1_0_0"
SUMMARY = OUT / "collector_methodology_sensitivity_review_summary.json"
PRODUCT = OUT / "collector_methodology_sensitivity_product_review.csv"
VARIANTS = OUT / "collector_methodology_sensitivity_variants.csv"
ROUTES = OUT / "collector_methodology_sensitivity_route_summary.csv"
DECISIONS = OUT / "collector_methodology_sensitivity_owner_decisions.csv"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    for path in [SUMMARY, PRODUCT, VARIANTS, ROUTES, DECISIONS]:
        if not path.exists():
            failures.append(f"missing_output:{path}")

    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    product = pd.read_csv(PRODUCT, low_memory=False)
    variants = pd.read_csv(VARIANTS, low_memory=False)
    routes = pd.read_csv(ROUTES, low_memory=False)
    decisions = pd.read_csv(DECISIONS, low_memory=False)

    if len(product) != 51:
        failures.append(f"product_count_expected_51_actual_{len(product)}")
    if product["canonical_tcgplayer_product_id"].astype(str).nunique() != 51:
        failures.append("product_identity_not_unique")
    if product["forecast_method_route"].nunique() != 4:
        failures.append("route_count_expected_4")
    if len(variants) != 51 * 7:
        failures.append(f"variant_row_count_expected_357_actual_{len(variants)}")
    if variants["variant_name"].nunique() != 7:
        failures.append("variant_count_expected_7")
    if not variants["retrospective_diagnostic_only"].map(truthy).all():
        failures.append("variant_status_not_diagnostic_only")
    if len(decisions) < 6:
        failures.append("owner_decision_register_incomplete")
    if not decisions["current_status"].astype(str).str.contains("PENDING|APPROVED_FORMULA_PENDING", regex=True).all():
        failures.append("owner_decision_status_invalid")
    if bool(summary.get("candidate_projection_authorized")):
        failures.append("candidate_projection_unexpectedly_authorized")
    if bool(summary.get("production_projection_authorized")):
        failures.append("production_projection_unexpectedly_authorized")
    if bool(summary.get("purchase_recommendation_authorized")):
        failures.append("purchase_recommendation_unexpectedly_authorized")
    if bool(summary.get("automatic_model_update_allowed")):
        failures.append("automatic_update_unexpectedly_allowed")
    if not bool(summary.get("future_information_prohibited")):
        failures.append("future_information_not_prohibited")

    result = {
        "audit_name": "Collector Methodology Sensitivity Review Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(product)),
        "variant_row_count": int(len(variants)),
        "route_count": int(product["forecast_method_route"].nunique()),
        "owner_decision_count": int(len(decisions)),
        "sensitivity_review_required_product_count": int(product["sensitivity_review_required"].map(truthy).sum()),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit validates diagnostic sensitivity outputs only. No alternative replaces the baseline and no forecast, purchase, or parameter authorization is granted."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
