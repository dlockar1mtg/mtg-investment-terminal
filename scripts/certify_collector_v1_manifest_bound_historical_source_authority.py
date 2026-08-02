from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_AUDIT = ROOT / "scripts/audit_collector_v1_chat_governance_conformance.py"
SNAPSHOT_PREFLIGHT = ROOT / "scripts/run_collector_v1_governance_locked_preflight.py"
SNAPSHOT_MANIFEST = ROOT / "data/governance/permanence/snapshots/collector-20260801T211201Z-7688afbd/collector_snapshot_manifest.json"
FROZEN_MANIFEST = ROOT / "data/governance/permanence/certification/collector_v1_frozen_history_source_manifest/collector_frozen_history_source_manifest.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_manifest_bound_historical_source_authority"

SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
RECORDED_AT_UTC = "2026-08-02T16:49:00+00:00"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_required(script: Path) -> tuple[bool, int]:
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False)
    return result.returncode == 0, result.returncode


def normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def snapshot_registry(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for item in payload.get("files", []):
        path = normalize(str(item.get("path", "")))
        if path:
            registry[path] = item
    return registry


def main() -> int:
    governance_ok, governance_code = run_required(GOVERNANCE_AUDIT)
    if not governance_ok:
        print(json.dumps({"status": "BLOCKED_GOVERNANCE_CONFORMANCE_FAILED", "exit_code": governance_code}, indent=2))
        return 2

    snapshot_ok, snapshot_code = run_required(SNAPSHOT_PREFLIGHT)
    if not snapshot_ok:
        print(json.dumps({"status": "BLOCKED_SNAPSHOT_CONFORMANCE_FAILED", "exit_code": snapshot_code}, indent=2))
        return 3

    for required in (SNAPSHOT_MANIFEST, FROZEN_MANIFEST):
        if not required.is_file():
            print(json.dumps({"status": "BLOCKED_REQUIRED_INPUT_MISSING", "missing": str(required.relative_to(ROOT))}, indent=2))
            return 4

    snapshot = json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8-sig"))
    boundary_failures: list[str] = []
    if snapshot.get("snapshot_id") != SNAPSHOT_ID:
        boundary_failures.append("SNAPSHOT_ID_MISMATCH")
    if snapshot.get("operating_date") != OPERATING_DATE:
        boundary_failures.append("OPERATING_DATE_MISMATCH")
    if snapshot.get("operating_timezone") != TIMEZONE:
        boundary_failures.append("TIMEZONE_MISMATCH")
    if snapshot.get("source_bundle_sha256") != BUNDLE_SHA:
        boundary_failures.append("SOURCE_BUNDLE_SHA256_MISMATCH")
    if snapshot.get("purchase_recommendations_authorized") is not False:
        boundary_failures.append("PURCHASE_AUTHORIZATION_MUST_REMAIN_FALSE")

    registered = snapshot_registry(snapshot)
    frozen_rows = read_csv(FROZEN_MANIFEST)
    registry: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    fields = [
        "source_file", "frozen_source_role", "snapshot_registered", "snapshot_role",
        "snapshot_operating_date", "snapshot_sha256", "current_sha256",
        "hash_matches_snapshot", "admitted_to_historical_source_authority",
        "adjudication_reasons", "raw_historical_price_authority_certified"
    ]

    for source in frozen_rows:
        rel = normalize(str(source.get("source_file", "")))
        frozen_role = str(source.get("source_role", "")).strip()
        item = registered.get(rel)
        path = ROOT / rel
        exists = path.is_file()
        current_hash = sha256(path) if exists else ""
        snapshot_hash = str(item.get("sha256", "")).lower() if item else ""
        snapshot_date = str(item.get("operating_date", "")) if item else ""
        reasons: list[str] = []

        if item is None:
            reasons.append("NOT_REGISTERED_IN_CERTIFIED_AUGUST1_MANIFEST")
        else:
            if snapshot_date != OPERATING_DATE:
                reasons.append("SOURCE_OPERATING_DATE_NOT_CERTIFIED_2026_08_01")
            if not exists:
                reasons.append("REGISTERED_SOURCE_FILE_MISSING")
            if not snapshot_hash:
                reasons.append("REGISTERED_SOURCE_SHA256_MISSING")
            if exists and snapshot_hash and current_hash.lower() != snapshot_hash:
                reasons.append("REGISTERED_SOURCE_HASH_MISMATCH")

        admitted = item is not None and not reasons
        row = {
            "source_file": rel,
            "frozen_source_role": frozen_role,
            "snapshot_registered": item is not None,
            "snapshot_role": str(item.get("role", "")) if item else "",
            "snapshot_operating_date": snapshot_date,
            "snapshot_sha256": snapshot_hash,
            "current_sha256": current_hash,
            "hash_matches_snapshot": bool(snapshot_hash and current_hash.lower() == snapshot_hash),
            "admitted_to_historical_source_authority": admitted,
            "adjudication_reasons": "|".join(reasons) if reasons else "REGISTERED_IN_CERTIFIED_AUGUST1_MANIFEST",
            "raw_historical_price_authority_certified": False,
        }
        (registry if admitted else exclusions).append(row)

    registry_path = OUT / "collector_manifest_bound_historical_source_registry.csv"
    exclusions_path = OUT / "collector_manifest_bound_historical_source_exclusions.csv"
    write_csv(registry_path, registry, fields)
    write_csv(exclusions_path, exclusions, fields)

    authoritative = [
        row for row in registry
        if row["frozen_source_role"] == "AUTHORITATIVE_PRICE_CANDIDATE"
    ]
    historical_available = len(authoritative) > 0
    source_adjudication_completed = not boundary_failures
    if boundary_failures:
        status = "FAIL_CERTIFIED_AUGUST1_SOURCE_BOUNDARY"
        exit_code = 5
    elif historical_available:
        status = "PASS_COLLECTOR_MANIFEST_BOUND_HISTORICAL_SOURCE_AUTHORITY"
        exit_code = 0
    else:
        status = "BLOCKED_NO_CERTIFIED_AUGUST1_HISTORICAL_PRICE_SOURCE"
        exit_code = 6

    summary = {
        "block_name": "Collector Manifest-Bound Historical Source Authority",
        "block_version": "2.0.0",
        "recorded_at_utc": RECORDED_AT_UTC,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "certified_snapshot_manifest_only": True,
        "prior_source_adjudication_revoked": True,
        "frozen_manifest_source_count": len(frozen_rows),
        "admitted_source_count": len(registry),
        "excluded_source_count": len(exclusions),
        "authoritative_price_candidate_count": len(authoritative),
        "source_adjudication_completed": source_adjudication_completed,
        "authoritative_historical_price_source_available": historical_available,
        "manifest_bound_historical_source_authority_certified": historical_available,
        "raw_historical_price_authority_certified": False,
        "historical_observation_ledger_build_authorized": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": boundary_failures,
        "status": status,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_manifest_bound_historical_source_authority_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
