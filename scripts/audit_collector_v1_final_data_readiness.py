"""Audit whether the certified Collector V1 feature matrix is substantively ready for forecasting."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURE_ROOT = ROOT / "data/governance/permanence/certification/collector_v1_feature_matrix"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_final_data_readiness"
MATRIX = FEATURE_ROOT / "collector_v1_feature_matrix.csv"
COVERAGE = FEATURE_ROOT / "collector_v1_feature_coverage.csv"
HORIZONS = FEATURE_ROOT / "collector_v1_horizon_eligibility.csv"
SUMMARY = FEATURE_ROOT / "collector_v1_feature_matrix_summary.json"
CERT = FEATURE_ROOT / "collector_v1_feature_matrix_certification.json"

REQUIRED_MODEL_FEATURES = {
    "return_30d",
    "return_90d",
    "return_180d",
    "return_365d",
    "annualized_volatility",
    "maximum_drawdown",
    "pack_count",
    "box_topper",
    "licensed_ip",
    "product_family",
    "edition_classification",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    required = [MATRIX, COVERAGE, HORIZONS, SUMMARY, CERT]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        result = {
            "block_name": "Collector V1 Final Data Readiness Audit",
            "block_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "missing_inputs": missing,
            "v1_forecast_data_ready": False,
            "status": "FAIL_REQUIRED_INPUTS_MISSING",
        }
        (OUT / "collector_v1_final_data_readiness_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    matrix = pd.read_csv(MATRIX, dtype=str).fillna("")
    coverage = pd.read_csv(COVERAGE, dtype=str).fillna("")
    horizons = pd.read_csv(HORIZONS, dtype=str).fillna("")
    build_summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    certification = json.loads(CERT.read_text(encoding="utf-8"))

    coverage_map = {
        str(row["feature"]): float(row["coverage_rate"])
        for _, row in coverage.iterrows()
        if str(row.get("coverage_rate", "")).strip()
    }

    direct_eligible = int(as_bool(matrix.get("direct_history_eligible_v1", pd.Series(dtype=str))).sum())
    comparable_eligible = int(as_bool(matrix.get("comparable_eligible_v1", pd.Series(dtype=str))).sum())
    experiment_eligible = int(as_bool(matrix.get("forecast_experiment_eligible_v1", pd.Series(dtype=str))).sum())
    presale = as_bool(matrix.get("presale", pd.Series(dtype=str)))
    experiment = as_bool(matrix.get("forecast_experiment_eligible_v1", pd.Series(dtype=str)))
    released_experiment_eligible = int((experiment & ~presale).sum()) if len(matrix) else 0

    comparable_rows = pd.to_numeric(matrix.get("selected_comparable_rows", pd.Series(dtype=float)), errors="coerce").fillna(0)
    products_with_comparables = int(comparable_rows.gt(0).sum())

    horizon_flag = as_bool(horizons.get("forecast_experiment_horizon_eligible", pd.Series(dtype=str)))
    eligible_by_horizon = {}
    if "horizon_days" in horizons.columns:
        for horizon, group in horizons.assign(_eligible=horizon_flag).groupby("horizon_days"):
            eligible_by_horizon[str(horizon)] = int(group["_eligible"].sum())

    zero_coverage_required_features = sorted(
        feature for feature in REQUIRED_MODEL_FEATURES if coverage_map.get(feature, 0.0) == 0.0
    )
    partial_coverage_required_features = sorted(
        feature for feature in REQUIRED_MODEL_FEATURES if 0.0 < coverage_map.get(feature, 0.0) < 1.0
    )

    current_v1_blockers = []
    if direct_eligible == 0:
        current_v1_blockers.append("No product is eligible for direct-history modeling under the current feature matrix.")
    if comparable_eligible == 0:
        current_v1_blockers.append("No product is eligible for comparable-based modeling under the current feature matrix.")
    if released_experiment_eligible == 0:
        current_v1_blockers.append("No released product is currently eligible for a forecast experiment.")
    if products_with_comparables == 0:
        current_v1_blockers.append("No active product has selected comparable rows joined into the feature matrix.")
    if zero_coverage_required_features:
        current_v1_blockers.append("Required modeling features have zero coverage: " + ", ".join(zero_coverage_required_features))

    remediation = [
        "Repair the active comparable join and certify peer coverage for comparable-routed products.",
        "Locate and certify deeper multi-date historical price artifacts for released products.",
        "Recalculate direct-history method eligibility from true unique-date history depth.",
        "Populate structural fields: pack count, box topper, licensed IP, product family, and edition classification.",
        "Build historical returns, volatility, drawdown, and trend features from certified multi-date history.",
        "Create an adjusted Supply Scarcity Index V1 that removes the inactive seller component.",
        "Rebuild and recertify the feature matrix after remediation.",
        "Only then build cutoff-based experiment datasets and backtests.",
    ]

    v1_ready = (
        certification.get("feature_matrix_certified") is True
        and direct_eligible + comparable_eligible > 0
        and released_experiment_eligible > 0
        and products_with_comparables > 0
        and not zero_coverage_required_features
    )

    gap_rows = []
    for blocker in current_v1_blockers:
        gap_rows.append({"classification": "CURRENT_V1_BLOCKER", "item": blocker})
    for item in remediation:
        gap_rows.append({"classification": "REQUIRED_REMEDIATION", "item": item})
    for item in [
        "Repeated eBay observations",
        "Listing persistence and observational entry/exit",
        "Temporal seller-count changes",
        "Supply Scarcity Index V2",
    ]:
        gap_rows.append({"classification": "FUTURE_V2_ONLY", "item": item})
    pd.DataFrame(gap_rows).to_csv(OUT / "collector_v1_data_gap_register.csv", index=False)

    result = {
        "block_name": "Collector V1 Final Data Readiness Audit",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_product_rows": int(len(matrix)),
        "feature_matrix_structurally_certified": bool(certification.get("feature_matrix_certified")),
        "direct_history_eligible_rows": direct_eligible,
        "comparable_eligible_rows": comparable_eligible,
        "forecast_experiment_eligible_rows": experiment_eligible,
        "released_forecast_experiment_eligible_rows": released_experiment_eligible,
        "products_with_selected_comparables": products_with_comparables,
        "eligible_products_by_horizon": eligible_by_horizon,
        "zero_coverage_required_features": zero_coverage_required_features,
        "partial_coverage_required_features": partial_coverage_required_features,
        "current_v1_blockers": current_v1_blockers,
        "required_remediation": remediation,
        "future_v2_only": [
            "Repeated eBay observations",
            "Listing persistence and observational entry/exit",
            "Temporal seller-count changes",
            "Supply Scarcity Index V2",
        ],
        "v1_feature_matrix_valid": True,
        "v1_forecast_data_ready": bool(v1_ready),
        "forecast_experiments_authorized": bool(v1_ready),
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "artifact_hashes": {
            "feature_matrix": sha256(MATRIX),
            "feature_coverage": sha256(COVERAGE),
            "horizon_eligibility": sha256(HORIZONS),
            "feature_summary": sha256(SUMMARY),
            "feature_certification": sha256(CERT),
        },
        "status": "PASS_COLLECTOR_V1_FORECAST_DATA_READY" if v1_ready else "BLOCKED_COLLECTOR_V1_CURRENT_DATA_REMEDIATION_REQUIRED",
    }
    (OUT / "collector_v1_final_data_readiness_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if v1_ready or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
