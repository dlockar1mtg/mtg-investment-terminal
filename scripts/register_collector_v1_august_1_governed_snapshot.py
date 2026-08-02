from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SOURCE_ID = "20260801T211201Z"
OPERATING_DATE = "2026-08-01"
OPERATING_TZ = ZoneInfo("America/Chicago")

REQUIRED = {
    "tcgcsv_manifest": "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z/tcgcsv_snapshot_manifest.json",
    "tcgcsv_products": "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z/tcgcsv_magic_products.csv",
    "tcgcsv_groups": "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z/tcgcsv_magic_groups.csv",
    "live_price_observations": "data/operations/tcgcsv/collector_live_price_observations.csv",
    "current_authority": "data/governance/permanence/certification/collector_current_authority/collector_current_authority_authorized.csv",
    "current_authority_summary": "data/governance/permanence/certification/collector_current_authority/collector_current_authority_summary.json",
    "live_price_candidates": "data/governance/permanence/certification/collector_live_current_prices/collector_live_current_price_certified_candidates.csv",
    "live_price_summary": "data/governance/permanence/certification/collector_live_current_prices/collector_live_current_price_summary.json",
    "ebay_listing_ledger": "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_accepted_listing_ledger.csv",
    "ebay_supply_snapshot": "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_product_supply_snapshot.csv",
    "ebay_baseline_summary": "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline/collector_ebay_day_one_supply_baseline_summary.json",
    "canonical_routes": "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_forecast_routes.csv",
    "canonical_history": "data/governance/permanence/certification/collector_v1_canonical_inputs/collector_v1_canonical_daily_price_history.csv",
    "feature_matrix": "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix.csv",
    "feature_manifest": "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix_manifest.json",
    "feature_certification": "data/governance/permanence/certification/collector_v1_feature_matrix/collector_v1_feature_matrix_certification.json",
}

EXPECTED_ROWS = {
    "tcgcsv_products": (100000, None),
    "tcgcsv_groups": (400, None),
    "live_price_observations": (50, 50),
    "current_authority": (50, 50),
    "live_price_candidates": (50, 50),
    "ebay_listing_ledger": (1, None),
    "ebay_supply_snapshot": (50, 50),
    "canonical_routes": (50, 51),
    "canonical_history": (1, None),
    "feature_matrix": (50, 50),
}

JSON_CONTROL_ROLES = {
    "tcgcsv_manifest",
    "current_authority_summary",
    "live_price_summary",
    "ebay_baseline_summary",
    "feature_manifest",
    "feature_certification",
}

EXPLICIT_FAILURE_KEYS = {
    "failed",
    "has_failures",
    "critical_failure",
    "critical_failures_present",
    "certification_failed",
    "validation_failed",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_count(path: Path) -> int | None:
    if path.suffix.lower() != ".csv":
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)


def local_operating_date(modified_utc: datetime) -> str:
    return modified_utc.astimezone(OPERATING_TZ).date().isoformat()


def json_control_result(path: Path) -> dict[str, object]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {
            "parseable": False,
            "explicit_failure": True,
            "status": None,
            "error": str(exc),
        }

    explicit_failure = False
    statuses: list[str] = []

    def walk(value: object, key: str = "") -> None:
        nonlocal explicit_failure
        normalized_key = key.lower()
        if normalized_key in EXPLICIT_FAILURE_KEYS and value not in (False, None, 0, "", [], {}):
            explicit_failure = True
        if normalized_key in {"status", "validation_status", "certification_status", "result"}:
            statuses.append(str(value))
            if "FAIL" in str(value).upper() or "ERROR" in str(value).upper():
                explicit_failure = True
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                walk(child_value, str(child_key))
        elif isinstance(value, list):
            for child_value in value:
                walk(child_value, key)

    walk(obj)
    return {
        "parseable": True,
        "explicit_failure": explicit_failure,
        "status": statuses,
        "error": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    checks: dict[str, bool] = {}
    files: list[dict[str, object]] = []
    json_controls: dict[str, dict[str, object]] = {}

    for role, rel in REQUIRED.items():
        path = ROOT / rel
        exists = path.exists()
        checks[f"{role}_exists"] = exists
        if not exists:
            continue

        modified_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        modified_local = modified_utc.astimezone(OPERATING_TZ)
        rows = row_count(path)
        files.append({
            "role": role,
            "path": rel,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "rows": rows,
            "last_modified_utc": modified_utc.isoformat(),
            "last_modified_operating_time": modified_local.isoformat(),
            "operating_date": modified_local.date().isoformat(),
        })

        checks[f"{role}_belongs_to_august_1_operating_cycle"] = (
            SNAPSHOT_SOURCE_ID in rel or local_operating_date(modified_utc) == OPERATING_DATE
        )

        if role in EXPECTED_ROWS:
            minimum, maximum = EXPECTED_ROWS[role]
            checks[f"{role}_row_coverage_valid"] = (
                rows is not None
                and rows >= minimum
                and (maximum is None or rows <= maximum)
            )

        if role in JSON_CONTROL_ROLES:
            result = json_control_result(path)
            json_controls[role] = result
            checks[f"{role}_json_parseable"] = bool(result["parseable"])
            checks[f"{role}_has_no_explicit_failure"] = not bool(result["explicit_failure"])

    source_roles = {
        "tcgcsv_products",
        "tcgcsv_groups",
        "live_price_observations",
        "current_authority",
        "live_price_candidates",
        "ebay_listing_ledger",
        "ebay_supply_snapshot",
    }
    source_files = [item for item in files if item["role"] in source_roles]
    digest = hashlib.sha256(
        "".join(sorted(str(item["sha256"]) for item in source_files)).encode("utf-8")
    ).hexdigest()
    snapshot_id = f"collector-{SNAPSHOT_SOURCE_ID}-{digest[:8]}"

    checks["all_required_authorities_present"] = all(
        checks.get(f"{role}_exists", False) for role in REQUIRED
    )
    checks["all_registered_artifacts_in_august_1_operating_cycle"] = all(
        checks.get(f"{role}_belongs_to_august_1_operating_cycle", False)
        for role in REQUIRED
    )
    checks["all_required_row_coverage_valid"] = all(
        checks.get(f"{role}_row_coverage_valid", False)
        for role in EXPECTED_ROWS
    )
    checks["all_json_controls_parseable"] = all(
        checks.get(f"{role}_json_parseable", False)
        for role in JSON_CONTROL_ROLES
    )
    checks["no_json_control_reports_explicit_failure"] = all(
        checks.get(f"{role}_has_no_explicit_failure", False)
        for role in JSON_CONTROL_ROLES
    )
    checks["source_hash_bundle_created"] = len(source_files) == len(source_roles) and bool(digest)

    certified = all(checks.values())
    out_dir = ROOT / "data/governance/permanence/snapshots" / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "snapshot_id": snapshot_id,
        "snapshot_source_id": SNAPSHOT_SOURCE_ID,
        "operating_date": OPERATING_DATE,
        "operating_timezone": "America/Chicago",
        "captured_at_utc": "2026-08-01T21:12:01Z",
        "captured_at_operating_time": "2026-08-01T16:12:01-05:00",
        "registered_at_utc": now.isoformat(),
        "provider_authorities": ["TCGCSV", "eBay"],
        "price_authority": REQUIRED["live_price_candidates"],
        "listing_authority": REQUIRED["ebay_listing_ledger"],
        "feature_authority": REQUIRED["feature_matrix"],
        "source_bundle_sha256": digest,
        "files": files,
        "json_control_results": json_controls,
        "checks": checks,
        "critical_failures": [name for name, passed in checks.items() if not passed],
        "certified_for_model_input": certified,
        "fresh_snapshot_capture_authorized": certified,
        "model_rebuild_authorized": certified,
        "purchase_recommendations_authorized": False,
        "status": (
            "PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION"
            if certified
            else "FAIL_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION"
        ),
    }

    manifest_path = out_dir / "collector_snapshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    evidence_dir = ROOT / "data/governance/permanence/certification/collector_v1_august_1_snapshot_registration"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_dir / "collector_v1_august_1_snapshot_registration_summary.json"
    summary_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    if certified:
        print("PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION")
        return 0
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
