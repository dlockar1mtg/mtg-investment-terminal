from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_snapshot_bound_current_foundation"
SUMMARY = OUT / "collector_v1_august1_snapshot_bound_current_foundation_summary.json"
FOUNDATION = OUT / "collector_v1_august1_snapshot_bound_current_foundation.csv"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
DIRECT_ROUTES = {"DIRECT_HISTORY_CALIBRATED", "DIRECT_HISTORY_LIMITED"}
COMPARABLE_ROUTES = {
    "COMPARABLE_PRODUCT_ADJUSTED",
    "EARLY_OPPORTUNITY_COHORT_FALLBACK",
    "FUNDAMENTAL_COMPARABLE_HYBRID",
}
GOVERNED_ROUTES = DIRECT_ROUTES | COMPARABLE_ROUTES


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().eq("true")


def falsy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().eq("false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    frame = pd.read_csv(FOUNDATION, dtype=str).fillna("") if FOUNDATION.exists() else pd.DataFrame()
    required = [
        "tcgplayer_product_id", "current_price", "source_observation_at_utc", "accepted_listing_count",
        "forecast_route", "history_observation_count", "history_requirement_status", "direct_history_required",
        "comparable_only_forecast_required", "confidence_penalty_required", "wider_uncertainty_required",
        "source_snapshot_id", "source_bundle_sha256", "source_price_authority_sha256",
        "source_listing_authority_sha256", "source_feature_authority_sha256", "model_generated_at_utc",
        "purchase_recommendation_authorized",
    ]

    columns_present = all(column in frame.columns for column in required)
    history_counts = pd.to_numeric(frame.get("history_observation_count", pd.Series(dtype=str)), errors="coerce")
    routes = frame.get("forecast_route", pd.Series(dtype=str)).astype(str).str.strip()
    direct_mask = routes.isin(DIRECT_ROUTES)
    comparable_mask = routes.isin(COMPARABLE_ROUTES)
    zero_history_mask = history_counts.fillna(-1).eq(0)

    direct_routes_have_history = bool(
        not frame.empty and columns_present and history_counts[direct_mask].gt(0).all()
    )
    zero_history_products_use_comparable_route = bool(
        not frame.empty and columns_present and comparable_mask[zero_history_mask].all()
    )
    zero_history_products_have_controls = bool(
        not frame.empty
        and columns_present
        and truthy(frame.loc[zero_history_mask, "comparable_only_forecast_required"]).all()
        and truthy(frame.loc[zero_history_mask, "confidence_penalty_required"]).all()
        and truthy(frame.loc[zero_history_mask, "wider_uncertainty_required"]).all()
        and falsy(frame.loc[zero_history_mask, "direct_history_required"]).all()
    )
    all_products_have_valid_history_disposition = bool(
        not frame.empty
        and columns_present
        and (
            (direct_mask & history_counts.gt(0))
            | (comparable_mask & history_counts.ge(0))
        ).all()
    )

    checks = {
        "summary_exists": SUMMARY.exists(),
        "foundation_exists": FOUNDATION.exists(),
        "builder_passed": summary.get("status") == "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION",
        "foundation_hash_matches_summary": bool(FOUNDATION.exists() and sha256(FOUNDATION) == summary.get("foundation_sha256")),
        "foundation_rows_50": len(frame) == 50,
        "product_ids_unique": bool(not frame.empty and "tcgplayer_product_id" in frame and not frame["tcgplayer_product_id"].duplicated().any()),
        "required_columns_present": columns_present,
        "required_values_complete": bool(not frame.empty and columns_present and all(frame[column].astype(str).str.strip().ne("").all() for column in required)),
        "all_snapshot_ids_match": bool(not frame.empty and "source_snapshot_id" in frame and frame["source_snapshot_id"].eq(SNAPSHOT_ID).all()),
        "all_prices_positive": bool(not frame.empty and "current_price" in frame and pd.to_numeric(frame["current_price"], errors="coerce").gt(0).all()),
        "all_listing_counts_nonnegative": bool(not frame.empty and "accepted_listing_count" in frame and pd.to_numeric(frame["accepted_listing_count"], errors="coerce").ge(0).all()),
        "all_routes_governed": bool(not frame.empty and routes.isin(GOVERNED_ROUTES).all()),
        "direct_history_routes_have_history": direct_routes_have_history,
        "zero_history_products_use_comparable_route": zero_history_products_use_comparable_route,
        "zero_history_products_have_uncertainty_controls": zero_history_products_have_controls,
        "all_products_have_valid_history_disposition": all_products_have_valid_history_disposition,
        "no_product_excluded_for_missing_direct_history": bool(len(frame) == 50),
        "purchase_authorization_false_for_all_rows": bool(not frame.empty and "purchase_recommendation_authorized" in frame and falsy(frame["purchase_recommendation_authorized"]).all()),
        "production_forecasting_not_yet_authorized": summary.get("production_forecasting_authorized") is False,
        "uip_delivery_not_yet_authorized": summary.get("uip_delivery_authorized") is False,
    }

    failures = [name for name, passed in checks.items() if not bool(passed)]
    certified = not failures
    certification = {
        "block_name": "Collector V1 August 1 Snapshot-Bound Current Foundation Certification",
        "block_version": "1.1.0",
        "governing_standard": "MTG_ANALYTICAL_CHARTER_v1.0.0_ROUTE_AWARE_MISSING_DATA_TREATMENT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_id": summary.get("source_snapshot_id"),
        "source_bundle_sha256": summary.get("source_bundle_sha256"),
        "foundation_path": summary.get("foundation_path"),
        "foundation_sha256": summary.get("foundation_sha256"),
        "products_with_direct_history": int(history_counts.gt(0).sum()) if not frame.empty else 0,
        "products_without_direct_history": int(zero_history_mask.sum()) if not frame.empty else 0,
        "direct_history_route_products": int(direct_mask.sum()) if not frame.empty else 0,
        "comparable_route_products": int(comparable_mask.sum()) if not frame.empty else 0,
        "total_checks": len(checks),
        "passed_checks": sum(bool(value) for value in checks.values()),
        "checks": {name: bool(value) for name, value in checks.items()},
        "critical_failures": failures,
        "current_foundation_certified": certified,
        "forecast_ranking_rebuild_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION_CERTIFICATION",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_v1_august1_snapshot_bound_current_foundation_certification.json").write_text(
        json.dumps(certification, indent=2), encoding="utf-8"
    )
    print(json.dumps(certification, indent=2))
    return 0 if certified or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
