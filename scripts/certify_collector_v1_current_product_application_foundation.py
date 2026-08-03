from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_product_application_foundation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = OUT_DIR / "collector_v1_current_product_application_foundation_summary.json"
    manifest_path = OUT_DIR / "collector_v1_current_product_authority_manifest.csv"
    diagnostics_path = OUT_DIR / "collector_v1_current_product_application_diagnostics.json"

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()

    checks = {
        "summary_exists": summary_path.exists(),
        "authority_manifest_exists": manifest_path.exists(),
        "diagnostics_exists": diagnostics_path.exists(),
        "decision_readiness_certified": bool(summary.get("checks", {}).get("decision_readiness_certified")),
        "four_authorities_listed": len(manifest) == 4,
        "four_authorities_resolved": bool(len(manifest) == 4 and manifest["resolved"].astype(str).str.lower().eq("true").all()),
        "governed_product_count_50": summary.get("governed_products") == 50,
        "all_products_priced": summary.get("products_with_positive_latest_price") == 50,
        "all_products_routed": summary.get("products_with_route_assignment") == 50,
        "foundation_ready": summary.get("current_product_application_foundation_ready") is True,
        "recommendations_still_blocked": summary.get("purchase_recommendations_authorized") is False,
        "production_still_blocked": summary.get("production_forecasting_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures

    certification = {
        "block_name": "Collector V1 Current Product Application Foundation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(bool(v) for v in checks.values()),
        "checks": checks,
        "critical_failures": failures,
        "current_product_application_foundation_certified": certified,
        "product_level_forecast_tournament_authorized": certified,
        "product_ranking_certified": False,
        "maximum_purchase_prices_certified": False,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Apply certified routes to all governed products and run product-level forecast, ranking, and purchase-price tournament",
        "status": "PASS_COLLECTOR_V1_CURRENT_PRODUCT_APPLICATION_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_CURRENT_PRODUCT_APPLICATION_FOUNDATION_CERTIFICATION",
    }
    (OUT_DIR / "collector_v1_current_product_application_foundation_certification.json").write_text(
        json.dumps(certification, indent=2), encoding="utf-8"
    )
    print(json.dumps(certification, indent=2))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
