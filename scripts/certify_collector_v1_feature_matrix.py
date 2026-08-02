"""Certify the governed English-only Collector V1 feature matrix."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/governance/permanence/certification/collector_v1_feature_matrix"
MATRIX = BASE / "collector_v1_feature_matrix.csv"
HORIZONS = BASE / "collector_v1_horizon_eligibility.csv"
SUMMARY = BASE / "collector_v1_feature_matrix_summary.json"
OUT = BASE / "collector_v1_feature_matrix_certification.json"


def add(checks: list[dict], name: str, passed: bool, details: str, severity: str = "CRITICAL") -> None:
    checks.append({"check": name, "passed": bool(passed), "severity": severity, "details": details})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    missing = [str(p.relative_to(ROOT)) for p in [MATRIX, HORIZONS, SUMMARY] if not p.is_file()]
    if missing:
        payload = {"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}
        print(json.dumps(payload, indent=2))
        return 1 if args.strict else 0

    matrix = pd.read_csv(MATRIX, dtype=str, encoding="utf-8-sig").fillna("")
    horizons = pd.read_csv(HORIZONS, dtype=str, encoding="utf-8-sig").fillna("")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    checks: list[dict] = []

    ids = matrix.get("tcgplayer_product_id", pd.Series(dtype=str)).astype(str).str.strip()
    add(checks, "exactly 50 active products", len(matrix) == 50, f"rows={len(matrix)}")
    add(checks, "50 unique product IDs", ids.nunique() == 50, f"unique={ids.nunique()}")
    add(checks, "no blank product IDs", ids.ne("").all(), f"blank={int(ids.eq('').sum())}")
    add(checks, "foreign-language product excluded", not ids.eq("628315").any(), f"matches={int(ids.eq('628315').sum())}")
    add(checks, "all rows have forecast method", matrix.get("forecast_method", pd.Series(dtype=str)).astype(str).str.strip().ne("").all(), "forecast_method")
    add(checks, "all rows have current price", pd.to_numeric(matrix.get("current_price", pd.Series(dtype=float)), errors="coerce").gt(0).all(), "current_price positive")
    add(checks, "scarcity coverage is complete", matrix.get("supply_scarcity_index_v1", pd.Series(dtype=str)).astype(str).str.strip().ne("").all(), "50/50 expected")
    scarcity = pd.to_numeric(matrix.get("supply_scarcity_index_v1", pd.Series(dtype=float)), errors="coerce")
    add(checks, "scarcity values bounded", scarcity.notna().all() and scarcity.between(0, 100).all(), f"min={scarcity.min()}, max={scarcity.max()}")
    seller_available = matrix.get("seller_feature_available", pd.Series(dtype=str)).astype(str).str.lower().isin(["true", "1", "yes"])
    add(checks, "seller feature explicitly disabled", not seller_available.any() and summary.get("seller_feature_policy") == "DISABLED_FOR_DIFFERENTIATION_IN_V1", f"usable_rows={int(seller_available.sum())}", "GOVERNED_GAP")
    add(checks, "all six horizons represented", set(pd.to_numeric(horizons.get("horizon_days", pd.Series(dtype=float)), errors="coerce").dropna().astype(int)) == {30, 90, 180, 365, 1095, 1825}, "30,90,180,365,1095,1825")
    add(checks, "horizon grid has 300 rows", len(horizons) == 300, f"rows={len(horizons)}")
    add(checks, "purchase recommendations remain blocked", not bool(summary.get("purchase_recommendations_authorized")), str(summary.get("purchase_recommendations_authorized")))
    add(checks, "UIP delivery remains blocked", not bool(summary.get("uip_delivery_authorized")), str(summary.get("uip_delivery_authorized")))

    critical_failures = [c for c in checks if c["severity"] == "CRITICAL" and not c["passed"]]
    governed_gaps = [c for c in checks if c["severity"] == "GOVERNED_GAP" and not c["passed"]]
    passed = len(critical_failures) == 0
    payload = {
        "block_name": "Collector V1 Feature Matrix Certification",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "critical_failures": critical_failures,
        "governed_gaps": governed_gaps,
        "feature_matrix_certified": passed,
        "forecast_experiments_authorized": passed,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "next_large_step": "Build cutoff-based forecast experiment datasets and run routed backtests" if passed else "Repair feature matrix critical failures",
        "status": "PASS_COLLECTOR_V1_FEATURE_MATRIX_CERTIFIED" if passed else "FAIL_COLLECTOR_V1_FEATURE_MATRIX_CERTIFICATION",
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(checks).to_csv(BASE / "collector_v1_feature_matrix_certification_checks.csv", index=False)
    print(json.dumps(payload, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
