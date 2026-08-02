from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_historical_observation_ledger_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_historical_observation_ledger"

LEDGER_FIELDS = [
    "ledger_observation_id",
    "governing_snapshot_id",
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "observation_date",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "selected_price",
    "selection_method",
    "price_data_quality",
    "source_name",
    "source_file_sha256",
    "candidate_history_sha256",
    "ledger_admission_status",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
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


def clean(value: Any) -> str:
    return str(value or "").strip()


def ledger_id(snapshot_id: str, canonical_id: str, observation_date: str) -> str:
    raw = f"{snapshot_id}|{canonical_id}|{observation_date}".encode("utf-8")
    return "COLLECTOR-HIST-" + hashlib.sha256(raw).hexdigest()[:24].upper()


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    cert_cfg = contract["row_level_certification"]
    candidate_path = ROOT / contract["candidate_history_path"]
    coverage_path = ROOT / contract["coverage_path"]
    cert_summary_path = ROOT / cert_cfg["summary_path"]
    failures: list[str] = []

    for path, code in [
        (candidate_path, "CANDIDATE_HISTORY_MISSING"),
        (coverage_path, "RECONSTRUCTION_COVERAGE_MISSING"),
        (cert_summary_path, "ROW_LEVEL_CERTIFICATION_SUMMARY_MISSING"),
    ]:
        if not path.is_file():
            failures.append(code)
    if failures:
        raise SystemExit(";".join(failures))

    cert_summary = json.loads(cert_summary_path.read_text(encoding="utf-8"))
    candidate_hash = sha256(candidate_path)
    if cert_summary.get("status") != cert_cfg["required_status"]:
        failures.append("ROW_LEVEL_CERTIFICATION_STATUS_INVALID")
    if cert_summary.get("row_level_reconstruction_certified") is not True:
        failures.append("ROW_LEVEL_RECONSTRUCTION_NOT_CERTIFIED")
    if cert_summary.get("historical_observation_ledger_build_authorized") is not True:
        failures.append("LEDGER_BUILD_NOT_AUTHORIZED")
    if candidate_hash != cert_cfg["candidate_history_sha256"]:
        failures.append("CANDIDATE_HISTORY_SHA256_MISMATCH")

    candidate_rows = read_csv(candidate_path)
    coverage_rows = read_csv(coverage_path)
    if len(candidate_rows) != cert_cfg["required_rows"]:
        failures.append("CANDIDATE_ROW_COUNT_MISMATCH")

    products = {clean(row.get("canonical_product_id")) for row in candidate_rows}
    dates = {clean(row.get("observation_date")) for row in candidate_rows}
    if len(products) != cert_cfg["required_products"]:
        failures.append("CANDIDATE_PRODUCT_COUNT_MISMATCH")
    if len(dates) != cert_cfg["required_dates"]:
        failures.append("CANDIDATE_DATE_COUNT_MISMATCH")

    key_counts = Counter(
        (clean(row.get("canonical_product_id")), clean(row.get("observation_date")))
        for row in candidate_rows
    )
    duplicate_key_count = sum(1 for count in key_counts.values() if count > 1)
    if duplicate_key_count:
        failures.append("DUPLICATE_LEDGER_PRODUCT_DATE_KEYS")

    no_history = [
        row for row in coverage_rows
        if clean(row.get("history_classification")) == "LEGITIMATE_POST_ARCHIVE_RELEASE_NO_HISTORY"
    ]
    if len(no_history) != contract["required_governed_no_history_products"]:
        failures.append("GOVERNED_NO_HISTORY_PRODUCT_COUNT_MISMATCH")
    elif clean(no_history[0].get("tcgplayer_product_id")) != contract["required_exception_tcgplayer_product_id"]:
        failures.append("GOVERNED_EXCEPTION_ID_MISMATCH")

    snapshot_id = contract["governing_snapshot_id"]
    ledger_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        canonical_id = clean(row.get("canonical_product_id"))
        observation_date = clean(row.get("observation_date"))
        selected_price = clean(row.get("selected_price"))
        if not selected_price or float(selected_price) <= 0:
            failures.append(f"INVALID_LEDGER_SELECTED_PRICE:{canonical_id}:{observation_date}")
        ledger_rows.append({
            **row,
            "ledger_observation_id": ledger_id(snapshot_id, canonical_id, observation_date),
            "governing_snapshot_id": snapshot_id,
            "candidate_history_sha256": candidate_hash,
            "ledger_admission_status": "ADMITTED_CERTIFIED_RECONSTRUCTION",
        })

    ledger_ids = [row["ledger_observation_id"] for row in ledger_rows]
    duplicate_ledger_id_count = len(ledger_ids) - len(set(ledger_ids))
    if duplicate_ledger_id_count:
        failures.append("DUPLICATE_LEDGER_OBSERVATION_IDS")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    ledger_path = OUTPUT / "collector_august1_historical_observation_ledger.csv"
    summary_path = OUTPUT / "collector_august1_historical_observation_ledger_summary.json"
    write_csv(ledger_path, ledger_rows, LEDGER_FIELDS)

    ledger_hash = sha256(ledger_path)
    summary = {
        "block_name": "Collector August 1 Historical Observation Ledger",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": snapshot_id,
        "candidate_history_sha256": candidate_hash,
        "row_level_certification_status": cert_summary.get("status"),
        "ledger_rows": len(ledger_rows),
        "ledger_products": len(products),
        "ledger_dates": len(dates),
        "governed_no_history_products": len(no_history),
        "duplicate_product_date_key_count": duplicate_key_count,
        "duplicate_ledger_observation_id_count": duplicate_ledger_id_count,
        "invalid_selected_price_count": sum(
            1 for row in ledger_rows if not clean(row.get("selected_price")) or float(row["selected_price"]) <= 0
        ),
        "ledger_sha256": ledger_hash,
        "historical_observation_ledger_built": not failures,
        "historical_observation_ledger_admitted": not failures,
        "historical_coverage_assessment_authorized": not failures,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": (
            "PASS_COLLECTOR_AUGUST1_HISTORICAL_OBSERVATION_LEDGER"
            if not failures
            else "FAIL_COLLECTOR_AUGUST1_HISTORICAL_OBSERVATION_LEDGER"
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
