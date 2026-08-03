from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE = ROOT / "scripts/audit_collector_v1_chat_governance_conformance.py"
RECONCILIATION = ROOT / "data/governance/permanence/certification/collector_v1_august1_provider_package_reconciliation_v1_1/collector_august1_provider_package_reconciliation_summary.json"
INVENTORY = ROOT / "data/governance/permanence/certification/collector_v1_august1_provider_package_reconciliation_v1_1/collector_august1_registered_file_inventory.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_reconstruction_scope"
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
RECORDED_AT_UTC = "2026-08-02T17:30:00+00:00"


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_governance() -> bool:
    return subprocess.run([sys.executable, str(GOVERNANCE)], cwd=ROOT, check=False).returncode == 0


def main() -> int:
    if not run_governance():
        return 2
    if not RECONCILIATION.is_file() or not INVENTORY.is_file():
        print(json.dumps({"status": "BLOCKED_REQUIRED_RECONCILIATION_INPUT_MISSING"}, indent=2))
        return 3

    recon = json.loads(RECONCILIATION.read_text(encoding="utf-8-sig"))
    inventory = read_csv(INVENTORY)
    failures: list[str] = []
    checks = {
        "RECONCILIATION_STATUS_INVALID": recon.get("status") == "PASS_COLLECTOR_AUGUST1_PROVIDER_PACKAGE_RECONCILIATION",
        "SNAPSHOT_ID_MISMATCH": recon.get("governing_snapshot_id") == SNAPSHOT_ID,
        "OPERATING_DATE_MISMATCH": recon.get("governing_operating_date") == OPERATING_DATE,
        "TIMEZONE_MISMATCH": recon.get("governing_timezone") == TIMEZONE,
        "BUNDLE_SHA_MISMATCH": recon.get("governing_source_bundle_sha256") == BUNDLE_SHA,
        "PRODUCT_COUNT_MISMATCH": recon.get("governing_certified_product_count") == PRODUCT_COUNT,
        "TCGPLAYER_COMPONENT_MISSING": recon.get("tcgplayer_tcgcsv_component_present") is True,
        "EBAY_COMPONENT_MISSING": recon.get("ebay_component_present") is True,
        "WIZARDS_RELEASE_DATE_AUTHORITY_MISSING": recon.get("wizards_release_date_authority_present") is True,
        "WIZARDS_RELEASE_DATE_COUNT_INVALID": recon.get("wizards_release_date_certified_product_count") == PRODUCT_COUNT,
        "RECONSTRUCTION_NOT_REQUIRED": recon.get("historical_reconstruction_required") is True,
    }
    failures.extend(reason for reason, passed in checks.items() if not passed)

    invalid_inventory = [row for row in inventory if row.get("snapshot_operating_date") != OPERATING_DATE or row.get("file_exists") != "True" or row.get("hash_matches_snapshot") != "True"]
    if invalid_inventory:
        failures.append("REGISTERED_AUGUST1_INVENTORY_INVALID")

    required_domains = {"TCGPLAYER_TCGCSV", "EBAY", "COLLECTOR_FOUNDATION"}
    present_domains = {row.get("provider_domain", "") for row in inventory}
    if not required_domains.issubset(present_domains):
        failures.append("REQUIRED_PROVIDER_DOMAIN_MISSING")

    scope_rows = [
        {
            "provider_domain": "TCGPLAYER_TCGCSV",
            "reconstruction_role": "AUTHORITATIVE_MARKET_PRICE_CANDIDATE",
            "identity_universe": "CERTIFIED_AUGUST1_50_PRODUCTS",
            "required_identity_field": "tcgplayer_product_id",
            "required_observation_date_semantics": "SOURCE_PROVIDED_HISTORICAL_OBSERVATION_DATE",
            "required_value_semantics": "TCGPLAYER_MARKET_PRICE",
            "minimum_distinct_observation_dates": 2,
            "older_output_artifact_allowed": False,
            "ledger_admission_authorized": False,
        },
        {
            "provider_domain": "EBAY",
            "reconstruction_role": "CORROBORATING_LISTING_SUPPLY_ONLY",
            "identity_universe": "CERTIFIED_AUGUST1_50_PRODUCTS",
            "required_identity_field": "canonical_product_id",
            "required_observation_date_semantics": "SOURCE_PROVIDED_LISTING_OBSERVATION_DATE",
            "required_value_semantics": "LISTING_PRICE_AND_SUPPLY_NOT_MARKET_PRICE",
            "minimum_distinct_observation_dates": 2,
            "older_output_artifact_allowed": False,
            "ledger_admission_authorized": False,
        },
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    scope_path = OUT / "collector_august1_historical_reconstruction_scope.csv"
    write_csv(scope_path, scope_rows, list(scope_rows[0]))

    failures = sorted(set(failures))
    summary = {
        "block_name": "Collector August 1 Historical Reconstruction Scope",
        "block_version": "1.0.0",
        "recorded_at_utc": RECORDED_AT_UTC,
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "provider_reconciliation_sha256": sha256(RECONCILIATION),
        "registered_inventory_sha256": sha256(INVENTORY),
        "reconstruction_scope_row_count": len(scope_rows),
        "tcgplayer_reconstruction_required": True,
        "ebay_reconstruction_required": True,
        "wizards_reconstruction_required": False,
        "older_output_artifact_use_authorized": False,
        "historical_reconstruction_scope_certified": not failures,
        "historical_source_reconstruction_authorized": not failures,
        "historical_observation_ledger_build_authorized": False,
        "raw_historical_price_authority_certified": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "scope_path": str(scope_path.relative_to(ROOT)),
        "scope_sha256": sha256(scope_path),
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_AUGUST1_HISTORICAL_RECONSTRUCTION_SCOPE" if not failures else "FAIL_COLLECTOR_AUGUST1_HISTORICAL_RECONSTRUCTION_SCOPE",
    }
    (OUT / "collector_august1_historical_reconstruction_scope_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 5


if __name__ == "__main__":
    raise SystemExit(main())
