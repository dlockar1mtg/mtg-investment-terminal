from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_tcgplayer_history_lineage_reproducibility_contract_v1.json"
GOVERNANCE = ROOT / "scripts/audit_collector_v1_chat_governance_conformance.py"
SCOPE_SUMMARY = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_reconstruction_scope/collector_august1_historical_reconstruction_scope_summary.json"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_tcgplayer_history_lineage_and_reproducibility"
SUMMARY = OUT / "collector_tcgplayer_history_lineage_and_reproducibility_summary.json"
INVENTORY = OUT / "collector_tcgplayer_history_lineage_inventory.csv"
REFERENCES = OUT / "collector_tcgplayer_history_direct_references.csv"

SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
PASS_STATUS = "PASS_COLLECTOR_TCGPLAYER_HISTORY_LINEAGE_AND_REPRODUCIBILITY"

TARGETS = [
    "data/operations/mtg_universal_history_ledger/universal_mtg_daily_consolidated_ledger.csv",
    "data/staging/purchase_refresh/2026-07-31/collector_history_rebuilt/product_master_model_input.csv",
    "scripts/build_canonical_governed_history.py",
    "scripts/certify_collector_booster_history.py",
    "scripts/run_collector_history_semantic_gate.py",
]

SCRIPT_TARGETS = [value for value in TARGETS if value.endswith(".py")]
CLASSIFICATIONS = {
    "CERTIFIABLE_EXISTING_TCGPLAYER_HISTORY",
    "REPRODUCIBLE_TCGPLAYER_HISTORY_SOURCE",
    "DERIVED_ONLY_NOT_AUTHORITY",
    "STALE_OUTPUT_NOT_PERMITTED",
    "IDENTITY_MISMATCH",
    "UNRESOLVED_LINEAGE",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    result = subprocess.run([sys.executable, str(GOVERNANCE)], cwd=ROOT, check=False)
    return result.returncode == 0


def csv_profile(path: Path) -> dict[str, Any]:
    rows = read_csv(path)
    headers = list(rows[0].keys()) if rows else []
    date_fields = [field for field in headers if "date" in field.lower() or "observed" in field.lower()]
    price_fields = [field for field in headers if "price" in field.lower() or "market" in field.lower()]
    identity_fields = [field for field in headers if field.lower().endswith("product_id") or field.lower() in {"canonical_product_id", "investment_product_id"}]
    source_fields = [field for field in headers if "source" in field.lower() or "lineage" in field.lower()]

    distinct_dates: set[str] = set()
    for row in rows:
        for field in date_fields:
            value = clean(row.get(field))
            if value:
                distinct_dates.add(value[:10])

    return {
        "rows": rows,
        "headers": headers,
        "row_count": len(rows),
        "date_fields": date_fields,
        "price_fields": price_fields,
        "identity_fields": identity_fields,
        "source_fields": source_fields,
        "distinct_observation_dates": len(distinct_dates),
    }


def extract_script_references(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    ast.parse(text)
    references: set[str] = set()

    for match in re.findall(r"[\"']([^\"']+(?:\.csv|\.json))[\"']", text):
        normalized = match.replace("\\", "/")
        if normalized.startswith(("data/", "config/", "artifacts/")):
            references.add(normalized)

    known_fragments = {
        "unified_mtg_product_registry.csv": "data/validation/phase_10/unified_mtg_registry/unified_mtg_product_registry.csv",
        "universal_mtg_historical_observation_ledger.csv": "data/operations/mtg_universal_history_ledger/universal_mtg_historical_observation_ledger.csv",
        "universal_mtg_daily_consolidated_ledger.csv": "data/operations/mtg_universal_history_ledger/universal_mtg_daily_consolidated_ledger.csv",
        "investment_products.csv": "data/product_master/investment_products.csv",
        "product_master_model_input.csv": "data/product_master/product_master_model_input.csv",
        "collector_booster_history_certification_v1.json": "config/mtg/governance/collector_booster_history_certification_v1.json",
        "collector_history_product_certification.csv": "data/operations/collector_booster_history_certification/candidate_v1_0_0/collector_history_product_certification.csv",
        "collector_history_certification_manifest.json": "data/operations/collector_booster_history_certification/candidate_v1_0_0/collector_history_certification_manifest.json",
    }
    for fragment, reference in known_fragments.items():
        if fragment in text:
            references.add(reference)

    return sorted(references)


def identity_values(rows: list[dict[str, str]], fields: list[str]) -> set[str]:
    values: set[str] = set()
    for row in rows:
        for field in fields:
            value = clean(row.get(field))
            if value:
                values.add(value)
    return values


def classify_csv(relative_path: str, profile: dict[str, Any], model_ids: set[str]) -> tuple[str, list[str]]:
    headers = set(profile["headers"])
    rows = profile["rows"]
    reasons: list[str] = []

    if "2026-07-31" in relative_path:
        return "STALE_OUTPUT_NOT_PERMITTED", ["JULY31_DERIVED_OUTPUT_CANNOT_SERVE_AS_AUTHORITY"]

    required_history_fields = bool(profile["date_fields"]) and bool(profile["price_fields"])
    source_lineage_present = bool(profile["source_fields"])
    if not required_history_fields:
        return "DERIVED_ONLY_NOT_AUTHORITY", ["HISTORICAL_DATE_OR_PRICE_SEMANTICS_MISSING"]

    if model_ids and profile["identity_fields"]:
        ledger_ids = identity_values(rows, profile["identity_fields"])
        if not (ledger_ids & model_ids):
            return "IDENTITY_MISMATCH", ["NO_IDENTITY_INTERSECTION_WITH_JULY31_COLLECTOR_INPUT"]

    source_text = "|".join(
        clean(row.get(field))
        for row in rows
        for field in profile["source_fields"]
    ).upper()
    tcgplayer_named = "TCGPLAYER" in source_text or "TCGCSV" in source_text
    ebay_named = "EBAY" in source_text

    if ebay_named and not tcgplayer_named:
        return "DERIVED_ONLY_NOT_AUTHORITY", ["EBAY_EVIDENCE_IS_NOT_HISTORICAL_MARKET_PRICE_AUTHORITY"]

    if not source_lineage_present:
        return "UNRESOLVED_LINEAGE", ["SOURCE_OR_LINEAGE_COLUMNS_ABSENT"]

    if not tcgplayer_named:
        return "UNRESOLVED_LINEAGE", ["TCGPLAYER_SOURCE_NOT_EXPLICITLY_IDENTIFIED"]

    if profile["distinct_observation_dates"] < 2:
        return "DERIVED_ONLY_NOT_AUTHORITY", ["FEWER_THAN_TWO_DISTINCT_SOURCE_DATES"]

    if {"source_file", "observation_date"}.issubset(headers):
        return "CERTIFIABLE_EXISTING_TCGPLAYER_HISTORY", ["TCGPLAYER_NAMED_WITH_SOURCE_FILE_AND_MULTI_DATE_HISTORY"]

    return "UNRESOLVED_LINEAGE", ["TCGPLAYER_NAMED_BUT_REPRODUCIBLE_UPSTREAM_FILE_NOT_PROVEN"]


def main() -> int:
    failures: list[str] = []
    if not CONTRACT.is_file() or not GOVERNANCE.is_file() or not SCOPE_SUMMARY.is_file():
        print(json.dumps({"status": "BLOCKED_REQUIRED_GOVERNANCE_INPUT_MISSING"}, indent=2))
        return 2

    if not run_governance():
        return 3

    contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
    scope = json.loads(SCOPE_SUMMARY.read_text(encoding="utf-8-sig"))

    checks = {
        "CONTRACT_SNAPSHOT_ID_MISMATCH": contract.get("governing_snapshot", {}).get("snapshot_id") == SNAPSHOT_ID,
        "CONTRACT_OPERATING_DATE_MISMATCH": contract.get("governing_snapshot", {}).get("operating_date") == OPERATING_DATE,
        "CONTRACT_TIMEZONE_MISMATCH": contract.get("governing_snapshot", {}).get("timezone") == TIMEZONE,
        "CONTRACT_BUNDLE_SHA_MISMATCH": contract.get("governing_snapshot", {}).get("source_bundle_sha256") == BUNDLE_SHA,
        "CONTRACT_PRODUCT_COUNT_MISMATCH": contract.get("governing_snapshot", {}).get("certified_product_count") == PRODUCT_COUNT,
        "SCOPE_STATUS_INVALID": scope.get("status") == "PASS_COLLECTOR_AUGUST1_HISTORICAL_RECONSTRUCTION_SCOPE",
        "SCOPE_SNAPSHOT_ID_MISMATCH": scope.get("governing_snapshot_id") == SNAPSHOT_ID,
        "SCOPE_PRODUCT_COUNT_MISMATCH": scope.get("governing_certified_product_count") == PRODUCT_COUNT,
        "SCOPE_LEDGER_ADMISSION_ALREADY_AUTHORIZED": scope.get("historical_observation_ledger_build_authorized") is False,
        "SCOPE_PURCHASES_ALREADY_AUTHORIZED": scope.get("purchase_recommendations_authorized") is False,
        "EBAY_HISTORY_REQUIREMENT_NOT_SUPERSEDED": contract.get("supersession", {}).get("ebay_historical_market_price_reconstruction_required") is False,
        "TCGPLAYER_ROLE_INVALID": contract.get("supersession", {}).get("tcgplayer_historical_market_price_authority_candidate") is True,
    }
    failures.extend(reason for reason, passed in checks.items() if not passed)

    missing_targets = [relative for relative in TARGETS if not (ROOT / relative).is_file()]
    failures.extend(f"BOUNDED_TARGET_MISSING:{relative}" for relative in missing_targets)

    inventory_rows: list[dict[str, Any]] = []
    reference_rows: list[dict[str, Any]] = []
    model_ids: set[str] = set()
    profiles: dict[str, dict[str, Any]] = {}

    july_model = ROOT / TARGETS[1]
    if july_model.is_file():
        profile = csv_profile(july_model)
        profiles[TARGETS[1]] = profile
        model_ids = identity_values(profile["rows"], profile["identity_fields"])

    for relative in TARGETS:
        path = ROOT / relative
        if not path.is_file():
            continue

        if path.suffix.lower() == ".csv":
            profile = profiles.get(relative) or csv_profile(path)
            profiles[relative] = profile
            classification, reasons = classify_csv(relative, profile, model_ids)
            inventory_rows.append({
                "path": relative,
                "file_type": "CSV",
                "sha256": sha256(path),
                "row_count": profile["row_count"],
                "distinct_observation_dates": profile["distinct_observation_dates"],
                "identity_fields": "|".join(profile["identity_fields"]),
                "date_fields": "|".join(profile["date_fields"]),
                "price_fields": "|".join(profile["price_fields"]),
                "source_fields": "|".join(profile["source_fields"]),
                "candidate_classification": classification,
                "classification_reasons": "|".join(reasons),
                "authority_admission_authorized": False,
            })
        else:
            try:
                references = extract_script_references(path)
                classification = "REPRODUCIBLE_TCGPLAYER_HISTORY_SOURCE" if references else "UNRESOLVED_LINEAGE"
                reasons = ["ACTIVE_SCRIPT_PARSES_AND_DIRECT_REFERENCES_CAPTURED"] if references else ["NO_DIRECT_DATA_REFERENCES_CAPTURED"]
            except (SyntaxError, UnicodeError) as exc:
                failures.append(f"ACTIVE_SCRIPT_PARSE_FAILED:{relative}:{type(exc).__name__}")
                references = []
                classification = "UNRESOLVED_LINEAGE"
                reasons = ["ACTIVE_SCRIPT_PARSE_FAILED"]

            inventory_rows.append({
                "path": relative,
                "file_type": "PYTHON",
                "sha256": sha256(path),
                "row_count": "",
                "distinct_observation_dates": "",
                "identity_fields": "",
                "date_fields": "",
                "price_fields": "",
                "source_fields": "",
                "candidate_classification": classification,
                "classification_reasons": "|".join(reasons),
                "authority_admission_authorized": False,
            })
            for reference in references:
                reference_path = ROOT / reference
                reference_rows.append({
                    "active_script": relative,
                    "direct_reference": reference,
                    "reference_exists": reference_path.is_file(),
                    "reference_sha256": sha256(reference_path) if reference_path.is_file() else "",
                    "reference_execution_authorized": False,
                    "reference_authority_status": "INSPECT_ONLY_NOT_AUTHORITY",
                })

    invalid_classifications = [row for row in inventory_rows if row["candidate_classification"] not in CLASSIFICATIONS]
    if invalid_classifications:
        failures.append("INVALID_CANDIDATE_CLASSIFICATION")

    missing_direct_references = [row for row in reference_rows if row["reference_exists"] is False]
    classification_counts = Counter(row["candidate_classification"] for row in inventory_rows)

    OUT.mkdir(parents=True, exist_ok=True)
    inventory_fields = [
        "path", "file_type", "sha256", "row_count", "distinct_observation_dates",
        "identity_fields", "date_fields", "price_fields", "source_fields",
        "candidate_classification", "classification_reasons", "authority_admission_authorized",
    ]
    write_csv(INVENTORY, inventory_rows, inventory_fields)
    reference_fields = [
        "active_script", "direct_reference", "reference_exists", "reference_sha256",
        "reference_execution_authorized", "reference_authority_status",
    ]
    write_csv(REFERENCES, reference_rows, reference_fields)

    failures = sorted(set(failures))
    summary = {
        "block_name": "Collector TCGplayer History Lineage and Reproducibility",
        "block_version": "1.0.0",
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "bounded_target_count": len(TARGETS),
        "bounded_targets_present": len(inventory_rows),
        "bounded_targets_missing": missing_targets,
        "active_script_count": len(SCRIPT_TARGETS),
        "direct_reference_count": len(reference_rows),
        "missing_direct_reference_count": len(missing_direct_references),
        "candidate_classification_counts": dict(sorted(classification_counts.items())),
        "universal_history_ledger_exists": (ROOT / TARGETS[0]).is_file(),
        "universal_history_ledger_rows": profiles.get(TARGETS[0], {}).get("row_count", 0),
        "universal_history_distinct_dates": profiles.get(TARGETS[0], {}).get("distinct_observation_dates", 0),
        "july31_model_input_exists": july_model.is_file(),
        "july31_model_input_rows": profiles.get(TARGETS[1], {}).get("row_count", 0),
        "july31_model_identity_count": len(model_ids),
        "tcgplayer_historical_market_price_authority_candidate": True,
        "ebay_historical_market_price_reconstruction_required": False,
        "ebay_supply_demand_liquidity_role_preserved": True,
        "lineage_and_reproducibility_audit_completed": not failures,
        "historical_reconstruction_execution_authorized": False,
        "historical_observation_ledger_build_authorized": False,
        "raw_historical_price_authority_certified": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "inventory_path": str(INVENTORY.relative_to(ROOT)),
        "inventory_sha256": sha256(INVENTORY),
        "direct_references_path": str(REFERENCES.relative_to(ROOT)),
        "direct_references_sha256": sha256(REFERENCES),
        "critical_failures": failures,
        "status": PASS_STATUS if not failures else "FAIL_COLLECTOR_TCGPLAYER_HISTORY_LINEAGE_AND_REPRODUCIBILITY",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 5


if __name__ == "__main__":
    raise SystemExit(main())
