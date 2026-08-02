from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_AUDIT = ROOT / "scripts/audit_collector_v1_chat_governance_conformance.py"
SNAPSHOT_PREFLIGHT = ROOT / "scripts/run_collector_v1_governance_locked_preflight.py"
SNAPSHOT_MANIFEST = ROOT / "data/governance/permanence/snapshots/collector-20260801T211201Z-7688afbd/collector_snapshot_manifest.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_provider_package_reconciliation"

SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
RECORDED_AT_UTC = "2026-08-02T17:00:00+00:00"

PATH_KEYS = ("path", "file", "file_path", "relative_path", "source_file")
HASH_KEYS = ("sha256", "file_sha256", "source_sha256", "hash")
ROLE_KEYS = ("role", "file_role", "source_role")
DATE_ALIASES = (
    "observation_date", "observed_at_utc", "observed_at", "source_timestamp",
    "collected_at", "snapshot_date", "as_of_date", "date", "release_date"
)
IDENTITY_ALIASES = (
    "canonical_product_id", "tcgplayer_product_id", "product_id", "box_name",
    "product_name", "name", "set_code"
)
PRICE_ALIASES = (
    "market_price", "tcg_market_price", "price", "low_price", "mid_price",
    "listing_price", "current_price"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_required(script: Path) -> tuple[bool, int]:
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False)
    return result.returncode == 0, result.returncode


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return ""


def provider_domain(path: str, role: str) -> str:
    text = f"{path} {role}".lower()
    if any(token in text for token in ("tcgcsv", "tcgplayer")):
        return "TCGPLAYER_TCGCSV"
    if any(token in text for token in ("wizard", "wotc", "release", "set_metadata", "product_catalog")):
        return "WIZARDS"
    if "ebay" in text:
        return "EBAY"
    return "COLLECTOR_FOUNDATION"


def first_alias(headers: list[str], aliases: tuple[str, ...]) -> str:
    lookup = {header.lower(): header for header in headers}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    return ""


def inspect_csv(path: Path) -> dict[str, Any]:
    rows = read_csv(path)
    headers = list(rows[0]) if rows else []
    date_field = first_alias(headers, DATE_ALIASES)
    identity_field = first_alias(headers, IDENTITY_ALIASES)
    price_field = first_alias(headers, PRICE_ALIASES)
    dates = sorted({str(row.get(date_field, "")).strip() for row in rows if date_field and str(row.get(date_field, "")).strip()})
    products = {str(row.get(identity_field, "")).strip() for row in rows if identity_field and str(row.get(identity_field, "")).strip()}
    historical = bool(date_field and len(dates) > 1 and dates[0][:10] < dates[-1][:10])
    return {
        "row_count_observed": len(rows),
        "column_count": len(headers),
        "identity_field": identity_field,
        "date_field": date_field,
        "price_field": price_field,
        "distinct_product_count_observed": len(products),
        "distinct_date_count": len(dates),
        "minimum_embedded_date": dates[0] if dates else "",
        "maximum_embedded_date": dates[-1] if dates else "",
        "contains_multi_date_history": historical,
    }


def main() -> int:
    governance_ok, governance_code = run_required(GOVERNANCE_AUDIT)
    if not governance_ok:
        print(json.dumps({"status": "BLOCKED_GOVERNANCE_CONFORMANCE_FAILED", "exit_code": governance_code}, indent=2))
        return 2
    snapshot_ok, snapshot_code = run_required(SNAPSHOT_PREFLIGHT)
    if not snapshot_ok:
        print(json.dumps({"status": "BLOCKED_SNAPSHOT_CONFORMANCE_FAILED", "exit_code": snapshot_code}, indent=2))
        return 3
    if not SNAPSHOT_MANIFEST.is_file():
        print(json.dumps({"status": "BLOCKED_SNAPSHOT_MANIFEST_MISSING"}, indent=2))
        return 4

    payload = json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8-sig"))
    failures: list[str] = []
    checks = {
        "SNAPSHOT_ID_MISMATCH": payload.get("snapshot_id") == SNAPSHOT_ID,
        "OPERATING_DATE_MISMATCH": payload.get("operating_date") == OPERATING_DATE,
        "TIMEZONE_MISMATCH": payload.get("operating_timezone") == TIMEZONE,
        "SOURCE_BUNDLE_SHA256_MISMATCH": payload.get("source_bundle_sha256") == BUNDLE_SHA,
        "SNAPSHOT_STATUS_INVALID": payload.get("status") == "PASS_COLLECTOR_V1_AUGUST_1_GOVERNED_SNAPSHOT_REGISTRATION",
    }
    failures.extend(reason for reason, passed in checks.items() if not passed)

    files = payload.get("files", [])
    if not isinstance(files, list) or not files:
        failures.append("REGISTERED_FILE_LIST_MISSING")
        files = []

    inventory: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            failures.append("REGISTERED_FILE_ENTRY_NOT_OBJECT")
            continue
        rel = str(first_value(item, PATH_KEYS)).replace("\\", "/").strip()
        registered_hash = str(first_value(item, HASH_KEYS)).lower().strip()
        role = str(first_value(item, ROLE_KEYS)).strip()
        domain = provider_domain(rel, role)
        path = ROOT / rel if rel else Path("")
        exists = bool(rel and path.is_file())
        current_hash = sha256(path) if exists else ""
        hash_matches = bool(exists and registered_hash and current_hash == registered_hash)
        inspection = {
            "row_count_observed": 0,
            "column_count": 0,
            "identity_field": "",
            "date_field": "",
            "price_field": "",
            "distinct_product_count_observed": 0,
            "distinct_date_count": 0,
            "minimum_embedded_date": "",
            "maximum_embedded_date": "",
            "contains_multi_date_history": False,
        }
        if exists and path.suffix.lower() == ".csv":
            try:
                inspection = inspect_csv(path)
            except (OSError, UnicodeDecodeError, csv.Error):
                failures.append(f"CSV_INSPECTION_FAILED:{rel}")
        if not rel:
            failures.append("REGISTERED_FILE_PATH_MISSING")
        if not exists:
            failures.append(f"REGISTERED_FILE_MISSING:{rel}")
        if not registered_hash:
            failures.append(f"REGISTERED_FILE_HASH_MISSING:{rel}")
        if exists and registered_hash and not hash_matches:
            failures.append(f"REGISTERED_FILE_HASH_MISMATCH:{rel}")
        inventory.append({
            "registered_path": rel,
            "registered_role": role,
            "provider_domain": domain,
            "snapshot_operating_date": OPERATING_DATE,
            "registered_sha256": registered_hash,
            "current_sha256": current_hash,
            "file_exists": exists,
            "hash_matches_snapshot": hash_matches,
            "registered_rows": item.get("rows", ""),
            **inspection,
            "historical_content_classification": (
                "MULTI_DATE_HISTORICAL_CONTENT" if inspection["contains_multi_date_history"]
                else "CURRENT_OR_REFERENCE_CONTENT"
            ),
        })

    domains = ("TCGPLAYER_TCGCSV", "WIZARDS", "EBAY", "COLLECTOR_FOUNDATION")
    provider_rows: list[dict[str, Any]] = []
    for domain in domains:
        matches = [row for row in inventory if row["provider_domain"] == domain]
        historical = [row for row in matches if row["contains_multi_date_history"]]
        provider_rows.append({
            "provider_domain": domain,
            "registered_file_count": len(matches),
            "hash_verified_file_count": sum(bool(row["hash_matches_snapshot"]) for row in matches),
            "multi_date_historical_file_count": len(historical),
            "provider_component_present": bool(matches),
            "historical_component_present": bool(historical),
            "reconstruction_required": domain in {"TCGPLAYER_TCGCSV", "EBAY"} and not historical,
            "reconciliation_status": "PRESENT" if matches else "MISSING_FROM_CERTIFIED_SNAPSHOT",
        })

    if not any(row["provider_domain"] == "TCGPLAYER_TCGCSV" for row in inventory):
        failures.append("TCGPLAYER_TCGCSV_COMPONENT_MISSING")
    if not any(row["provider_domain"] == "WIZARDS" for row in inventory):
        failures.append("WIZARDS_COMPONENT_MISSING")
    if not any(row["provider_domain"] == "EBAY" for row in inventory):
        failures.append("EBAY_COMPONENT_MISSING")

    OUT.mkdir(parents=True, exist_ok=True)
    inventory_fields = list(inventory[0]) if inventory else [
        "registered_path", "registered_role", "provider_domain", "snapshot_operating_date",
        "registered_sha256", "current_sha256", "file_exists", "hash_matches_snapshot"
    ]
    inventory_path = OUT / "collector_august1_registered_file_inventory.csv"
    provider_path = OUT / "collector_august1_provider_coverage.csv"
    write_csv(inventory_path, inventory, inventory_fields)
    write_csv(provider_path, provider_rows, list(provider_rows[0]))

    failures = sorted(set(failures))
    reconciliation_complete = not failures
    summary = {
        "block_name": "Collector August 1 Provider Package Reconciliation",
        "block_version": "1.0.0",
        "recorded_at_utc": RECORDED_AT_UTC,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "snapshot_manifest_only_discovery": True,
        "registered_file_count": len(inventory),
        "provider_file_counts": dict(sorted(Counter(row["provider_domain"] for row in inventory).items())),
        "tcgplayer_tcgcsv_component_present": any(row["provider_domain"] == "TCGPLAYER_TCGCSV" for row in inventory),
        "wizards_component_present": any(row["provider_domain"] == "WIZARDS" for row in inventory),
        "ebay_component_present": any(row["provider_domain"] == "EBAY" for row in inventory),
        "tcgplayer_historical_component_present": any(row["provider_domain"] == "TCGPLAYER_TCGCSV" and row["contains_multi_date_history"] for row in inventory),
        "ebay_historical_component_present": any(row["provider_domain"] == "EBAY" and row["contains_multi_date_history"] for row in inventory),
        "provider_package_reconciliation_completed": reconciliation_complete,
        "historical_reconstruction_required": any(row["reconstruction_required"] for row in provider_rows),
        "historical_source_reconstruction_authorized": False,
        "historical_observation_ledger_build_authorized": False,
        "raw_historical_price_authority_certified": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "inventory_path": str(inventory_path.relative_to(ROOT)),
        "inventory_sha256": sha256(inventory_path),
        "provider_coverage_path": str(provider_path.relative_to(ROOT)),
        "provider_coverage_sha256": sha256(provider_path),
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_AUGUST1_PROVIDER_PACKAGE_RECONCILIATION" if reconciliation_complete else "FAIL_COLLECTOR_AUGUST1_PROVIDER_PACKAGE_RECONCILIATION",
    }
    summary_path = OUT / "collector_august1_provider_package_reconciliation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if reconciliation_complete else 5


if __name__ == "__main__":
    raise SystemExit(main())
