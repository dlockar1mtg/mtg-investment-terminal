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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    frame = pd.read_csv(FOUNDATION, dtype=str).fillna("") if FOUNDATION.exists() else pd.DataFrame()
    required = [
        "tcgplayer_product_id", "current_price", "source_observation_at_utc", "accepted_listing_count",
        "forecast_route", "history_observation_count", "source_snapshot_id", "source_bundle_sha256",
        "source_price_authority_sha256", "source_listing_authority_sha256", "source_feature_authority_sha256",
        "model_generated_at_utc", "purchase_recommendation_authorized",
    ]
    checks = {
        "summary_exists": SUMMARY.exists(),
        "foundation_exists": FOUNDATION.exists(),
        "builder_passed": summary.get("status") == "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION",
        "foundation_hash_matches_summary": bool(FOUNDATION.exists() and sha256(FOUNDATION) == summary.get("foundation_sha256")),
        "foundation_rows_50": len(frame) == 50,
        "product_ids_unique": bool(not frame.empty and not frame["tcgplayer_product_id"].duplicated().any()),
        "required_columns_present": all(column in frame.columns for column in required),
        "required_values_complete": bool(not frame.empty and all(frame[column].astype(str).str.strip().ne("").all() for column in required)),
        "all_snapshot_ids_match": bool(not frame.empty and frame["source_snapshot_id"].eq("collector-20260801T211201Z-7688afbd").all()),
        "all_prices_positive": bool(not frame.empty and pd.to_numeric(frame["current_price"], errors="coerce").gt(0).all()),
        "all_listing_counts_nonnegative": bool(not frame.empty and pd.to_numeric(frame["accepted_listing_count"], errors="coerce").ge(0).all()),
        "all_history_counts_positive": bool(not frame.empty and pd.to_numeric(frame["history_observation_count"], errors="coerce").gt(0).all()),
        "purchase_authorization_false_for_all_rows": bool(not frame.empty and frame["purchase_recommendation_authorized"].astype(str).str.lower().eq("false").all()),
        "production_remains_blocked": summary.get("production_forecasting_authorized") is False,
        "uip_delivery_remains_blocked": summary.get("uip_delivery_authorized") is False,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures
    certification = {
        "block_name": "Collector V1 August 1 Snapshot-Bound Current Foundation Certification",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_id": summary.get("source_snapshot_id"),
        "source_bundle_sha256": summary.get("source_bundle_sha256"),
        "foundation_path": summary.get("foundation_path"),
        "foundation_sha256": summary.get("foundation_sha256"),
        "total_checks": len(checks),
        "passed_checks": sum(bool(value) for value in checks.values()),
        "checks": checks,
        "critical_failures": failures,
        "current_foundation_certified": certified,
        "forecast_ranking_rebuild_authorized": certified,
        "production_forecasting_authorized": False,
        "purchase_recommendations_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_AUGUST1_SNAPSHOT_BOUND_CURRENT_FOUNDATION_CERTIFICATION",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_v1_august1_snapshot_bound_current_foundation_certification.json").write_text(json.dumps(certification, indent=2), encoding="utf-8")
    print(json.dumps(certification, indent=2))
    return 0 if certified or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
