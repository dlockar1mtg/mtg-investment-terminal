from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_AUDIT = ROOT / "scripts" / "audit_collector_v1_chat_governance_conformance.py"
SNAPSHOT_PREFLIGHT = ROOT / "scripts" / "run_collector_v1_governance_locked_preflight.py"
SNAPSHOT_MANIFEST = ROOT / "data/governance/permanence/snapshots/collector-20260801T211201Z-7688afbd/collector_snapshot_manifest.json"
FROZEN_MANIFEST = ROOT / "data/governance/permanence/certification/collector_v1_frozen_history_source_manifest/collector_frozen_history_source_manifest.csv"
FROZEN_SUMMARY = ROOT / "data/governance/permanence/certification/collector_v1_frozen_history_source_manifest/collector_frozen_history_source_manifest_summary.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_manifest_bound_historical_source_authority"

SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
RECORDED_AT_UTC = "2026-08-02T16:34:00+00:00"

ADMITTED_ROLES = {"AUTHORITATIVE_PRICE_CANDIDATE", "CORROBORATING_LISTING_ONLY"}
IDENTITY_ALIASES = (
    "canonical_product_id", "tcgplayer_product_id", "product_id", "product_name", "name"
)
DATE_ALIASES = (
    "observation_date", "observed_at_utc", "observed_at", "snapshot_date", "date", "captured_at_utc"
)
MARKET_PRICE_ALIASES = (
    "market_price", "tcg_market_price", "marketprice", "price", "low_price", "listing_price"
)
PROHIBITED_PATH_TERMS = (
    "secret_lair", "pre_collector", "recommendation", "forecast", "ranking", "evaluation",
    "model_output", "portfolio", "owned_inventory", "backup", "attempt", "repair", "staging"
)


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


def first_header(path: Path) -> list[str]:
    if path.suffix.lower() != ".csv":
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return [str(value).strip() for value in next(reader, [])]


def first_alias(headers: list[str], aliases: tuple[str, ...]) -> str:
    lookup = {header.lower(): header for header in headers}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    return ""


def run_required(script: Path) -> tuple[bool, int]:
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False)
    return result.returncode == 0, result.returncode


def validate_snapshot_manifest() -> list[str]:
    failures: list[str] = []
    try:
        payload = json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"SNAPSHOT_MANIFEST_READ_ERROR:{type(exc).__name__}"]
    checks = {
        "SNAPSHOT_ID_MISMATCH": payload.get("snapshot_id") == SNAPSHOT_ID,
        "OPERATING_DATE_MISMATCH": payload.get("operating_date") == OPERATING_DATE,
        "TIMEZONE_MISMATCH": payload.get("operating_timezone") == TIMEZONE,
        "SOURCE_BUNDLE_SHA256_MISMATCH": payload.get("source_bundle_sha256") == BUNDLE_SHA,
        "PURCHASE_AUTHORIZATION_MUST_REMAIN_FALSE": payload.get("purchase_recommendations_authorized") is False,
        "SNAPSHOT_REGISTRATION_STATUS_INVALID": payload.get("status") == "PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION",
    }
    for reason, passed in checks.items():
        if not passed:
            failures.append(reason)
    row_50_roles = {
        item.get("role") for item in payload.get("files", [])
        if item.get("rows") == PRODUCT_COUNT
    }
    required_roles = {
        "live_price_observations", "current_authority", "live_price_candidates",
        "ebay_supply_snapshot", "feature_matrix"
    }
    if not required_roles.issubset(row_50_roles):
        failures.append("CERTIFIED_50_PRODUCT_COVERAGE_NOT_PROVEN")
    return failures


def main() -> int:
    governance_ok, governance_code = run_required(GOVERNANCE_AUDIT)
    if not governance_ok:
        print(json.dumps({"status": "BLOCKED_GOVERNANCE_CONFORMANCE_FAILED", "exit_code": governance_code}, indent=2))
        return 2

    snapshot_ok, snapshot_code = run_required(SNAPSHOT_PREFLIGHT)
    if not snapshot_ok:
        print(json.dumps({"status": "BLOCKED_SNAPSHOT_CONFORMANCE_FAILED", "exit_code": snapshot_code}, indent=2))
        return 3

    required = [SNAPSHOT_MANIFEST, FROZEN_MANIFEST, FROZEN_SUMMARY]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print(json.dumps({"status": "BLOCKED_REQUIRED_INPUT_MISSING", "missing": missing}, indent=2))
        return 4

    critical_failures = validate_snapshot_manifest()
    frozen_summary = json.loads(FROZEN_SUMMARY.read_text(encoding="utf-8-sig"))
    if frozen_summary.get("status") != "PASS_COLLECTOR_V1_FROZEN_HISTORY_SOURCE_MANIFEST":
        critical_failures.append("FROZEN_SOURCE_MANIFEST_NOT_CERTIFIED")
    if frozen_summary.get("manifest_sha256") != sha256(FROZEN_MANIFEST):
        critical_failures.append("FROZEN_SOURCE_MANIFEST_HASH_MISMATCH")

    frozen_rows = read_csv(FROZEN_MANIFEST)
    registry: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    for source in frozen_rows:
        rel = str(source.get("source_file", "")).replace("\\", "/").strip()
        role = str(source.get("source_role", "")).strip()
        path = ROOT / rel
        exists = path.is_file()
        current_hash = sha256(path) if exists else ""
        frozen_hash = str(source.get("source_sha256", "")).lower().strip()
        headers = first_header(path) if exists else []
        identity_field = first_alias(headers, IDENTITY_ALIASES)
        date_field = first_alias(headers, DATE_ALIASES)
        price_field = first_alias(headers, MARKET_PRICE_ALIASES)
        ledger_price_fields = str(source.get("ledger_price_fields", "")).strip()
        if not price_field and ledger_price_fields:
            price_field = ledger_price_fields.split("|")[0]
        provider = str(source.get("ledger_source_names", "")).strip()
        if not provider:
            provider = "eBay" if "ebay" in rel.lower() else ("TCGCSV" if "tcgcsv" in rel.lower() else "")

        reasons: list[str] = []
        if role not in ADMITTED_ROLES:
            reasons.append(f"ROLE_NOT_ADMITTED:{role or 'BLANK'}")
        if any(term in rel.lower() for term in PROHIBITED_PATH_TERMS):
            reasons.append("PROHIBITED_SOURCE_PATH_SEMANTICS")
        if not exists:
            reasons.append("SOURCE_FILE_MISSING")
        if not frozen_hash:
            reasons.append("FROZEN_SOURCE_HASH_MISSING")
        if exists and frozen_hash and current_hash != frozen_hash:
            reasons.append("SOURCE_HASH_DRIFT")
        if role in ADMITTED_ROLES and not provider:
            reasons.append("PROVIDER_IDENTITY_MISSING")
        if role in ADMITTED_ROLES and not identity_field:
            reasons.append("IDENTITY_FIELD_MISSING")
        if role in ADMITTED_ROLES and not date_field:
            reasons.append("OBSERVATION_DATE_FIELD_MISSING")
        if role in ADMITTED_ROLES and not price_field:
            reasons.append("PRICE_FIELD_MISSING")
        if role in ADMITTED_ROLES and not str(source.get("first_observation_date", "")).strip():
            reasons.append("MINIMUM_OBSERVATION_DATE_MISSING")
        if role in ADMITTED_ROLES and not str(source.get("last_observation_date", "")).strip():
            reasons.append("MAXIMUM_OBSERVATION_DATE_MISSING")
        if role == "AUTHORITATIVE_PRICE_CANDIDATE" and "ebay" in (provider + rel).lower():
            reasons.append("EBAY_CANNOT_BE_AUTHORITATIVE_PRICE")
        if role == "CORROBORATING_LISTING_ONLY" and "ebay" not in (provider + rel).lower():
            reasons.append("CORROBORATING_LISTING_PROVIDER_NOT_EBAY")

        admitted = role in ADMITTED_ROLES and not reasons
        row = {
            "source_file": rel,
            "source_sha256": current_hash,
            "frozen_source_sha256": frozen_hash,
            "hash_matches_frozen_manifest": bool(current_hash and current_hash == frozen_hash),
            "source_role": role,
            "provider": provider,
            "identity_field": identity_field,
            "observation_date_field": date_field,
            "price_field": price_field,
            "minimum_observation_date": source.get("first_observation_date", ""),
            "maximum_observation_date": source.get("last_observation_date", ""),
            "row_count": source.get("row_count", ""),
            "distinct_product_count": source.get("distinct_product_count", ""),
            "admitted_to_historical_source_authority": admitted,
            "authority_limit": "MARKET_PRICE_CANDIDATE" if role == "AUTHORITATIVE_PRICE_CANDIDATE" else ("LISTING_CORROBORATION_ONLY" if role == "CORROBORATING_LISTING_ONLY" else "NOT_ADMITTED"),
            "adjudication_reasons": "|".join(reasons) if reasons else "ADMITTED_BY_FROZEN_MANIFEST_AND_IMMUTABLE_LINEAGE",
            "raw_historical_price_authority_certified": False,
        }
        if admitted:
            registry.append(row)
        else:
            exclusions.append(row)
            if role in ADMITTED_ROLES:
                critical_failures.append(f"ADMISSIBLE_ROLE_SOURCE_FAILED_CONTROLS:{rel}:{'|'.join(reasons)}")

    if not registry:
        critical_failures.append("NO_HISTORICAL_SOURCE_AUTHORITY_ADMITTED")
    if any(row["source_role"] == "AUTHORITATIVE_PRICE_CANDIDATE" and "ebay" in (str(row["provider"]) + str(row["source_file"])).lower() for row in registry):
        critical_failures.append("EBAY_ADMITTED_AS_AUTHORITATIVE_PRICE")

    fields = [
        "source_file", "source_sha256", "frozen_source_sha256", "hash_matches_frozen_manifest",
        "source_role", "provider", "identity_field", "observation_date_field", "price_field",
        "minimum_observation_date", "maximum_observation_date", "row_count", "distinct_product_count",
        "admitted_to_historical_source_authority", "authority_limit", "adjudication_reasons",
        "raw_historical_price_authority_certified"
    ]
    registry_path = OUT / "collector_manifest_bound_historical_source_registry.csv"
    exclusions_path = OUT / "collector_manifest_bound_historical_source_exclusions.csv"
    write_csv(registry_path, registry, fields)
    write_csv(exclusions_path, exclusions, fields)

    critical_failures = sorted(set(critical_failures))
    summary = {
        "block_name": "Collector Manifest-Bound Historical Source Authority",
        "block_version": "1.0.0",
        "recorded_at_utc": RECORDED_AT_UTC,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "frozen_manifest_path": str(FROZEN_MANIFEST.relative_to(ROOT)),
        "frozen_manifest_sha256": sha256(FROZEN_MANIFEST),
        "frozen_manifest_source_count": len(frozen_rows),
        "admitted_source_count": len(registry),
        "excluded_source_count": len(exclusions),
        "authoritative_price_candidate_count": sum(row["source_role"] == "AUTHORITATIVE_PRICE_CANDIDATE" for row in registry),
        "corroborating_listing_source_count": sum(row["source_role"] == "CORROBORATING_LISTING_ONLY" for row in registry),
        "registry_path": str(registry_path.relative_to(ROOT)),
        "registry_sha256": sha256(registry_path),
        "exclusions_path": str(exclusions_path.relative_to(ROOT)),
        "exclusions_sha256": sha256(exclusions_path),
        "open_ended_repository_scan_used": False,
        "manifest_bound_historical_source_authority_certified": not critical_failures,
        "raw_historical_price_authority_certified": False,
        "historical_observation_ledger_build_authorized": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": critical_failures,
        "status": "PASS_COLLECTOR_MANIFEST_BOUND_HISTORICAL_SOURCE_AUTHORITY" if not critical_failures else "FAIL_COLLECTOR_MANIFEST_BOUND_HISTORICAL_SOURCE_AUTHORITY",
    }
    summary_path = OUT / "collector_manifest_bound_historical_source_authority_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not critical_failures else 5


if __name__ == "__main__":
    raise SystemExit(main())
