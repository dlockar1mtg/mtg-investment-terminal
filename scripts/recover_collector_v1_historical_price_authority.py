from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_price_recovery"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
SOURCE_BUNDLE_SHA256 = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
CERTIFIED_PRODUCT_COUNT = 50
REVOCATION_RECORDED_AT_UTC = "2026-08-02T15:23:00+00:00"


def main() -> int:
    parser = argparse.ArgumentParser(description="Revoked Collector historical recovery entrypoint.")
    parser.add_argument("--strict", action="store_true")
    parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "block_name": "Collector V1 Historical Price Recovery and Coverage",
        "block_version": "1.0.2-revoked",
        "generated_at_utc": REVOCATION_RECORDED_AT_UTC,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": SOURCE_BUNDLE_SHA256,
        "governing_certified_product_count": CERTIFIED_PRODUCT_COUNT,
        "previous_result_revoked": True,
        "revoked_status": "PASS_COLLECTOR_V1_HISTORICAL_PRICE_RECOVERY_AND_COVERAGE",
        "revocation_reasons": [
            "RECOVERY_DID_NOT_LOAD_CERTIFIED_AUGUST_1_SNAPSHOT_FIRST",
            "RECOVERY_DID_NOT_VERIFY_SOURCE_BUNDLE_SHA256",
            "RECOVERY_USED_168_PRODUCTS_INSTEAD_OF_CERTIFIED_50",
            "RECOVERY_USED_CURRENT_CLOCK_INSTEAD_OF_GOVERNED_OPERATING_DATE",
            "RECOVERY_ALLOWED_MISSING_RELEASE_DATES",
            "RECOVERY_CONFLATED_SOURCE_DISCOVERY_WITH_SNAPSHOT_LINEAGE",
            "HISTORICAL_AUTHORITY_RULE_WAS_INSUFFICIENT"
        ],
        "raw_historical_price_authority_certified": False,
        "historical_coverage_assessment_completed": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "status": "BLOCKED_PENDING_AUGUST_1_SNAPSHOT_CONFORMANCE"
    }
    (OUTPUT / "collector_historical_price_recovery_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
