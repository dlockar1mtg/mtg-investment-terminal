from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
LINEAGE_SUMMARY = ROOT / "data/governance/permanence/certification/collector_v1_august1_price_observation_lineage/collector_v1_august1_price_observation_lineage_summary.json"
MANIFEST = ROOT / "data/governance/permanence/snapshots" / SNAPSHOT_ID / "collector_snapshot_manifest.json"
OUT = ROOT / "data/governance/permanence/authority/collector_v1_current_data_authority_active.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    failures: list[str] = []
    try:
        lineage = json.loads(LINEAGE_SUMMARY.read_text(encoding="utf-8-sig"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        if lineage.get("status") != "PASS_COLLECTOR_V1_AUGUST1_PRICE_OBSERVATION_LINEAGE":
            failures.append("price observation lineage is not certified")
        if lineage.get("source_snapshot_id") != SNAPSHOT_ID:
            failures.append("lineage snapshot mismatch")
        if manifest.get("certified_for_model_input") is not True:
            failures.append("snapshot not certified for model input")
        if manifest.get("model_rebuild_authorized") is not True:
            failures.append("snapshot model rebuild not authorized")
        record = {
            "authority_record_version": "2.0.0",
            "activated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "ACTIVE_AUGUST1_SNAPSHOT_BOUND_MODEL_INPUT_AUTHORITY" if not failures else "BLOCKED_AUGUST1_AUTHORITY_ACTIVATION",
            "supersedes_status": "BLOCKED_PENDING_APPROVED_EXECUTABLE_PRICE_ADAPTER",
            "providers": ["TCGCSV", "eBay"],
            "source_snapshot_id": SNAPSHOT_ID,
            "source_bundle_sha256": manifest.get("source_bundle_sha256"),
            "price_authority": lineage.get("lineage_enriched_price_authority_path"),
            "source_price_authority_sha256": lineage.get("source_price_authority_sha256"),
            "source_price_observation_authority_sha256": lineage.get("source_price_observation_authority_sha256"),
            "listing_authority": manifest.get("listing_authority"),
            "supply_authority": next((x.get("path") for x in manifest.get("files", []) if x.get("role") == "ebay_supply_snapshot"), None),
            "feature_authority": manifest.get("feature_authority"),
            "route_authority": next((x.get("path") for x in manifest.get("files", []) if x.get("role") == "canonical_routes"), None),
            "historical_authority": next((x.get("path") for x in manifest.get("files", []) if x.get("role") == "canonical_history"), None),
            "model_input_authorized": not failures,
            "snapshot_bound_model_rebuild_authorized": not failures,
            "purchase_recommendations_authorized": False,
            "production_forecasting_authorized": False,
            "uip_delivery_authorized": False,
            "critical_failures": failures,
        }
    except Exception as exc:
        failures = [str(exc)]
        record = {
            "authority_record_version": "2.0.0",
            "activated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_AUGUST1_AUTHORITY_ACTIVATION",
            "source_snapshot_id": SNAPSHOT_ID,
            "model_input_authorized": False,
            "snapshot_bound_model_rebuild_authorized": False,
            "purchase_recommendations_authorized": False,
            "production_forecasting_authorized": False,
            "uip_delivery_authorized": False,
            "critical_failures": failures,
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    passed = not failures
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
