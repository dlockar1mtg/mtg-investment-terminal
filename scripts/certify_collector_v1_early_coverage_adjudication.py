from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_early_coverage_adjudication"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_early_coverage_adjudication_summary.json"
    product_path = OUT_DIR / "collector_v1_early_product_coverage_adjudication.csv"
    reason_path = OUT_DIR / "collector_v1_early_coverage_reason_counts.csv"

    failures: list[dict] = []
    if not summary_path.exists():
        failures.append({"check": "summary exists", "severity": "CRITICAL"})
    if not product_path.exists():
        failures.append({"check": "product adjudication exists", "severity": "CRITICAL"})
    if not reason_path.exists():
        failures.append({"check": "reason counts exist", "severity": "CRITICAL"})

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    products = pd.read_csv(product_path) if product_path.exists() else pd.DataFrame()

    checks = [
        ("all 40 cutoff products profiled", int(summary.get("products_profiled", 0)) == 40, f"products={summary.get('products_profiled')}"),
        ("eligible and excluded totals reconcile", int(summary.get("eligible_products", 0)) + int(summary.get("excluded_products", 0)) == int(summary.get("products_profiled", 0)), "totals"),
        ("every product has exclusion reason", not products.empty and products["exclusion_reason"].notna().all(), "reasons"),
        ("peer count column resolved", bool(summary.get("peer_count_column")), str(summary.get("peer_count_column"))),
        ("peer median column resolved", bool(summary.get("peer_median_column")), str(summary.get("peer_median_column"))),
        ("promotion remains blocked", summary.get("model_promotion_authorized") is False, str(summary.get("model_promotion_authorized"))),
        ("purchase remains blocked", summary.get("purchase_recommendations_authorized") is False, str(summary.get("purchase_recommendations_authorized"))),
    ]
    for name, passed, details in checks:
        if not passed:
            failures.append({"check": name, "severity": "CRITICAL", "details": details})

    certified = not failures
    result = {
        "block_name": "Collector V1 Early Opportunity Coverage Adjudication Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks) + 3,
        "critical_failures": failures,
        "early_coverage_adjudication_certified": certified,
        "source_remediation_authorized": certified,
        "model_promotion_authorized": False,
        "long_horizon_simulation_authorized": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_EARLY_COVERAGE_ADJUDICATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_EARLY_COVERAGE_ADJUDICATION_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_early_coverage_adjudication_certification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if certified or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
