from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_v1_authoritative_feature_foundation"
SUMMARY = BASE / "collector_v1_authoritative_feature_foundation_summary.json"
MATRIX = BASE / "collector_v1_authoritative_feature_matrix.csv"
LINEAGE = BASE / "collector_v1_source_to_feature_lineage.csv"
COVERAGE = BASE / "collector_v1_authoritative_feature_coverage.csv"
MANIFEST = BASE / "collector_v1_authority_input_manifest.csv"
OUT = BASE / "collector_v1_authoritative_feature_foundation_certification.json"
CHECKS = BASE / "collector_v1_authoritative_feature_foundation_checks.csv"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    required = [SUMMARY, MATRIX, LINEAGE, COVERAGE, MANIFEST]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    checks = []

    def add(name: str, passed: bool, details: str, severity: str = "CRITICAL"):
        checks.append({"check": name, "passed": bool(passed), "severity": severity, "details": details})

    add("all authoritative foundation artifacts exist", not missing, f"missing={missing}")
    if missing:
        result = {
            "block_name": "Collector V1 Authoritative Feature Foundation Certification",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "critical_failures": [c for c in checks if not c["passed"] and c["severity"] == "CRITICAL"],
            "authoritative_feature_foundation_certified": False,
            "forecast_experiments_authorized": False,
            "production_forecasting_authorized": False,
            "purchase_recommendations_authorized": False,
            "uip_delivery_authorized": False,
            "status": "FAIL_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION_CERTIFICATION",
        }
        BASE.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(checks).to_csv(CHECKS, index=False)
        OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    matrix = pd.read_csv(MATRIX, low_memory=False)
    lineage = pd.read_csv(LINEAGE, low_memory=False)
    coverage = pd.read_csv(COVERAGE, low_memory=False)
    manifest = pd.read_csv(MANIFEST, low_memory=False)

    add("active universe has exactly 50 rows", len(matrix) == 50, f"rows={len(matrix)}")
    add("active universe has 50 unique product IDs", matrix.get("tcgplayer_product_id", pd.Series(dtype=str)).astype(str).nunique() == 50, f"unique={matrix.get('tcgplayer_product_id', pd.Series(dtype=str)).astype(str).nunique()}")
    add("no excluded Japanese product remains", not matrix.astype(str).apply(lambda c: c.str.contains("628315|TCGCSV-24219-628315", regex=True, na=False)).any().any(), "excluded_product=628315")
    add("all registered authority inputs are manifested", len(manifest) >= 10 and manifest["sha256"].astype(str).str.len().eq(64).all(), f"manifest_rows={len(manifest)}")
    add("source-to-feature lineage is present", len(lineage) >= 12, f"lineage_rows={len(lineage)}")
    add("lineage contains no unresolved source columns", not lineage["source_column"].astype(str).eq("UNRESOLVED").any(), f"unresolved={lineage.loc[lineage['source_column'].astype(str).eq('UNRESOLVED'), 'feature'].tolist()}")
    add("authoritative current prices cover all products", matrix.get("current_price_authoritative", pd.Series(dtype=float)).notna().all(), f"missing={int(matrix.get('current_price_authoritative', pd.Series(dtype=float)).isna().sum())}")
    add("safe monthly history joins to active products", int(summary.get("history_diagnostics", {}).get("covered_active_products", 0)) > 0, f"covered={summary.get('history_diagnostics', {}).get('covered_active_products', 0)}")
    add("comparable evidence joins to active products", int(summary.get("comparable_diagnostics", {}).get("covered_active_products", 0)) > 0, f"covered={summary.get('comparable_diagnostics', {}).get('covered_active_products', 0)}")
    add("at least one released modeling route is supported", int(summary.get("direct_history_eligible_rows", 0)) + int(summary.get("comparable_eligible_rows", 0)) > 0, f"direct={summary.get('direct_history_eligible_rows', 0)}, comparable={summary.get('comparable_eligible_rows', 0)}")
    add("builder reported no blockers", not summary.get("blockers"), f"blockers={summary.get('blockers', [])}")
    add("foundation summary reports readiness", bool(summary.get("authoritative_feature_foundation_ready")), f"status={summary.get('status')}")

    coverage_map = coverage.set_index("feature")["coverage_rate"].to_dict() if not coverage.empty else {}
    add("release authority covers all products", float(coverage_map.get("release_date_authoritative", 0)) == 1.0, f"coverage={coverage_map.get('release_date_authoritative', 0)}")
    add("scarcity V1 covers all products", float(coverage_map.get("supply_scarcity_index_v1", 0)) == 1.0, f"coverage={coverage_map.get('supply_scarcity_index_v1', 0)}")

    critical_failures = [c for c in checks if not c["passed"] and c["severity"] == "CRITICAL"]
    certified = not critical_failures
    result = {
        "block_name": "Collector V1 Authoritative Feature Foundation Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "critical_failures": critical_failures,
        "authoritative_feature_foundation_certified": certified,
        "forecast_experiments_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build governed historical cutoff experiment datasets" if certified else "Resolve authoritative join or lineage failures",
        "status": "PASS_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_AUTHORITATIVE_FEATURE_FOUNDATION_CERTIFICATION",
    }
    pd.DataFrame(checks).to_csv(CHECKS, index=False)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if args.strict and not certified else 0


if __name__ == "__main__":
    raise SystemExit(main())
