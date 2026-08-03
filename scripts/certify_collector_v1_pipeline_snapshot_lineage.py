from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/collector_snapshot_contract_v1.json"
OUT_ROOT = ROOT / "data/governance/permanence/certification/collector_v1_pipeline_lineage"

FEATURE_PATH = ROOT / "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix.csv"
FOUNDATION_DIR = ROOT / "data/governance/permanence/certification/collector_v1_current_product_application_foundation"
RANK_DIR = ROOT / "data/governance/permanence/certification/collector_v1_product_level_forecast_ranking_tournament"
PURCHASE_DIR = ROOT / "data/governance/permanence/certification/collector_v1_final_purchase_adequacy_tournament_v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: object) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-manifest", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    manifest_path = Path(args.snapshot_manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    snapshot_id = str(manifest.get("snapshot_id", "UNRESOLVED"))
    out_dir = OUT_ROOT / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)

    required_fields = contract["required_manifest_fields"]
    manifest_fields_present = all(field in manifest for field in required_fields)
    snapshot_id_valid = bool(re.fullmatch(contract["snapshot_id_pattern"], snapshot_id))
    manifest_sha = sha256(manifest_path) if manifest_path.exists() else None

    captured_at = parse_utc(manifest.get("captured_at_utc"))
    maximum_observation = parse_utc(manifest.get("maximum_source_observation_at_utc"))
    minimum_observation = parse_utc(manifest.get("minimum_source_observation_at_utc"))
    freshness_cutoff = parse_utc(manifest.get("freshness_cutoff_utc"))

    source_files = manifest.get("source_files", []) if isinstance(manifest.get("source_files", []), list) else []
    source_results: list[dict] = []
    for item in source_files:
        relative = item.get("path") if isinstance(item, dict) else None
        expected = item.get("sha256") if isinstance(item, dict) else None
        path = ROOT / relative if relative else None
        actual = sha256(path) if path and path.exists() else None
        source_results.append({
            "path": relative,
            "exists": bool(path and path.exists()),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "hash_matches": bool(expected and actual and expected == actual),
        })
    source_hashes_match = bool(source_results) and all(row["hash_matches"] for row in source_results)

    feature_exists = FEATURE_PATH.exists()
    feature = pd.read_csv(FEATURE_PATH) if feature_exists else pd.DataFrame()
    feature_count_ok = len(feature) == int(contract["required_product_count"])
    feature_dates = pd.to_datetime(feature.get("latest_price_date"), utc=True, errors="coerce") if feature_exists else pd.Series(dtype="datetime64[ns, UTC]")
    feature_dates_present = bool(len(feature_dates) and feature_dates.notna().all())
    feature_max_date = feature_dates.max() if feature_dates_present else None
    feature_not_newer_than_source = bool(feature_max_date is not None and maximum_observation is not None and feature_max_date <= maximum_observation)
    feature_fresh_for_purchase = bool(
        feature_dates_present
        and freshness_cutoff is not None
        and feature_dates.ge(freshness_cutoff).all()
    )

    declared_feature_hash = manifest.get("feature_matrix_sha256")
    actual_feature_hash = sha256(FEATURE_PATH) if feature_exists else None
    feature_hash_matches = bool(declared_feature_hash and actual_feature_hash == declared_feature_hash)

    downstream_paths = {
        "foundation_summary": FOUNDATION_DIR / "collector_v1_current_product_application_foundation_summary.json",
        "ranking_summary": RANK_DIR / "collector_v1_product_level_forecast_ranking_tournament_summary.json",
        "purchase_summary": PURCHASE_DIR / "collector_v1_final_purchase_adequacy_summary_v2.json",
    }
    downstream_rows: list[dict] = []
    required_lineage = contract["required_downstream_lineage_fields"]
    for stage, path in downstream_paths.items():
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        missing = [field for field in required_lineage if field not in payload]
        downstream_rows.append({
            "stage": stage,
            "path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "source_snapshot_id": payload.get("source_snapshot_id"),
            "lineage_fields_complete": not missing,
            "missing_lineage_fields": missing,
            "snapshot_matches": payload.get("source_snapshot_id") == snapshot_id,
            "manifest_hash_matches": payload.get("source_snapshot_manifest_sha256") == manifest_sha,
            "feature_hash_matches": payload.get("source_feature_matrix_sha256") == actual_feature_hash,
        })

    downstream_lineage_complete = bool(downstream_rows) and all(row["lineage_fields_complete"] for row in downstream_rows)
    downstream_snapshot_consistent = bool(downstream_rows) and all(row["snapshot_matches"] for row in downstream_rows)
    downstream_hashes_consistent = bool(downstream_rows) and all(
        row["manifest_hash_matches"] and row["feature_hash_matches"] for row in downstream_rows
    )

    checks = {
        "snapshot_manifest_exists": manifest_path.exists(),
        "snapshot_manifest_fields_present": manifest_fields_present,
        "snapshot_id_valid": snapshot_id_valid,
        "snapshot_certified_for_model_input": manifest.get("certified_for_model_input") is True,
        "captured_at_present": captured_at is not None,
        "source_observation_range_present": maximum_observation is not None and minimum_observation is not None,
        "capture_not_before_source_observation": bool(captured_at and maximum_observation and captured_at >= maximum_observation),
        "source_files_declared_and_hashes_match": source_hashes_match,
        "feature_matrix_exists": feature_exists,
        "feature_product_count_50": feature_count_ok,
        "feature_price_dates_present": feature_dates_present,
        "feature_dates_not_newer_than_source": feature_not_newer_than_source,
        "feature_matrix_hash_matches_manifest": feature_hash_matches,
        "all_current_features_within_purchase_freshness_window": feature_fresh_for_purchase,
        "downstream_lineage_fields_complete": downstream_lineage_complete,
        "downstream_snapshot_id_consistent": downstream_snapshot_consistent,
        "downstream_source_hashes_consistent": downstream_hashes_consistent,
    }
    failures = [name for name, passed in checks.items() if not passed]
    certified = not failures

    certification = {
        "block_name": "Collector V1 End-to-End Snapshot and Lineage Certification",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": snapshot_id,
        "snapshot_manifest": str(manifest_path.relative_to(ROOT)) if manifest_path.exists() and manifest_path.is_relative_to(ROOT) else str(manifest_path),
        "snapshot_manifest_sha256": manifest_sha,
        "source_results": source_results,
        "downstream_results": downstream_rows,
        "checks": checks,
        "critical_failures": failures,
        "pipeline_snapshot_lineage_certified": certified,
        "purchase_recommendations_authorized": certified,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_V1_PIPELINE_SNAPSHOT_LINEAGE_CERTIFIED" if certified else "FAIL_COLLECTOR_V1_PIPELINE_SNAPSHOT_LINEAGE_CERTIFICATION",
    }
    output = out_dir / "collector_v1_pipeline_lineage_certification.json"
    output.write_text(json.dumps(certification, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(source_results).to_csv(out_dir / "collector_v1_snapshot_source_hash_checks.csv", index=False)
    pd.DataFrame(downstream_rows).to_csv(out_dir / "collector_v1_downstream_lineage_checks.csv", index=False)
    print(json.dumps(certification, indent=2, default=str))
    return 0 if (certified or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
