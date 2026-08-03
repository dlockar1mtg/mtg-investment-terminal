from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_row_level_reconstruction_certification_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_row_level_reconstruction_certification"

ROW_FIELDS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "observation_date",
    "candidate_selected_price",
    "source_selected_price",
    "candidate_selection_method",
    "source_selection_method",
    "candidate_source_sha256",
    "source_file_sha256",
    "row_fingerprint_match",
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


def clean(value: Any) -> str:
    return str(value or "").strip()


def fingerprint(row: dict[str, str], fields: list[str]) -> str:
    payload = "|".join(clean(row.get(field)) for field in fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    expected = contract["expected"]
    failures: list[str] = []

    summary_path = ROOT / contract["reconstruction_summary_path"]
    history_path = ROOT / contract["reconstructed_history_path"]
    coverage_path = ROOT / contract["coverage_path"]
    source_path = ROOT / contract["certified_archive_source_path"]

    required = [summary_path, history_path, coverage_path, source_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_INPUTS:" + ";".join(missing))

    reconstruction_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if reconstruction_summary.get("status") != "PASS_COLLECTOR_AUGUST1_IDENTITY_AUTHORITY_AND_RECONSTRUCTION":
        failures.append("RECONSTRUCTION_PREREQUISITE_NOT_PASS")
    if reconstruction_summary.get("row_level_reconstruction_certification_authorized") is not True:
        failures.append("ROW_LEVEL_CERTIFICATION_NOT_AUTHORIZED")

    candidate_rows = read_csv(history_path)
    coverage_rows = read_csv(coverage_path)
    source_rows = read_csv(source_path)

    archive_ids = {
        clean(row.get("tcgplayer_product_id"))
        for row in coverage_rows
        if clean(row.get("history_classification")) == "CERTIFIED_TCGCSV_ARCHIVE_HISTORY"
    }
    no_history_rows = [
        row for row in coverage_rows
        if clean(row.get("history_classification")) == "LEGITIMATE_POST_ARCHIVE_RELEASE_NO_HISTORY"
    ]

    if len(candidate_rows) != expected["reconstructed_rows"]:
        failures.append("RECONSTRUCTED_ROW_COUNT_MISMATCH")
    if len(archive_ids) != expected["archive_backed_products"]:
        failures.append("ARCHIVE_BACKED_PRODUCT_COUNT_MISMATCH")
    if len(no_history_rows) != expected["governed_no_history_products"]:
        failures.append("NO_HISTORY_PRODUCT_COUNT_MISMATCH")
    if len(no_history_rows) == 1 and clean(no_history_rows[0].get("tcgplayer_product_id")) != expected["exception_tcgplayer_product_id"]:
        failures.append("NO_HISTORY_EXCEPTION_ID_MISMATCH")

    source_subset = [
        row for row in source_rows
        if clean(row.get("tcgplayer_product_id")) in archive_ids
    ]

    candidate_key_fields = ["tcgplayer_product_id", "observation_date"]
    source_key_fields = ["tcgplayer_product_id", "observation_date"]
    semantic_fields = [
        "tcgplayer_product_id",
        "observation_date",
        "market_price",
        "low_price",
        "mid_price",
        "high_price",
        "direct_low_price",
        "selected_price",
        "selection_method",
        "price_data_quality",
    ]

    candidate_by_key = {
        tuple(clean(row.get(field)) for field in candidate_key_fields): row
        for row in candidate_rows
    }
    source_by_key = {
        tuple(clean(row.get(field)) for field in source_key_fields): row
        for row in source_subset
    }

    candidate_duplicates = Counter(
        tuple(clean(row.get(field)) for field in candidate_key_fields)
        for row in candidate_rows
    )
    source_duplicates = Counter(
        tuple(clean(row.get(field)) for field in source_key_fields)
        for row in source_subset
    )
    duplicate_candidate_keys = sum(1 for count in candidate_duplicates.values() if count > 1)
    duplicate_source_keys = sum(1 for count in source_duplicates.values() if count > 1)
    if duplicate_candidate_keys:
        failures.append("DUPLICATE_CANDIDATE_KEYS")
    if duplicate_source_keys:
        failures.append("DUPLICATE_SOURCE_KEYS")

    missing_candidate_keys = sorted(set(source_by_key) - set(candidate_by_key))
    extra_candidate_keys = sorted(set(candidate_by_key) - set(source_by_key))
    if missing_candidate_keys:
        failures.append("SOURCE_ROWS_MISSING_FROM_CANDIDATE")
    if extra_candidate_keys:
        failures.append("CANDIDATE_ROWS_NOT_IN_SOURCE")

    reconciliation: list[dict[str, Any]] = []
    mismatched_rows = 0
    for key in sorted(set(source_by_key) | set(candidate_by_key)):
        candidate = candidate_by_key.get(key, {})
        source = source_by_key.get(key, {})
        candidate_fp = fingerprint(candidate, semantic_fields) if candidate else ""
        source_fp = fingerprint(source, semantic_fields) if source else ""
        matched = bool(candidate and source and candidate_fp == source_fp)
        if not matched:
            mismatched_rows += 1
        reconciliation.append({
            "canonical_product_id": clean(candidate.get("canonical_product_id")),
            "tcgplayer_product_id": key[0],
            "observation_date": key[1],
            "candidate_selected_price": clean(candidate.get("selected_price")),
            "source_selected_price": clean(source.get("selected_price")),
            "candidate_selection_method": clean(candidate.get("selection_method")),
            "source_selection_method": clean(source.get("selection_method")),
            "candidate_source_sha256": clean(candidate.get("source_file_sha256")),
            "source_file_sha256": sha256(source_path) if source else "",
            "row_fingerprint_match": matched,
        })

    if mismatched_rows:
        failures.append("ROW_FINGERPRINT_MISMATCH")

    distinct_dates = {clean(row.get("observation_date")) for row in candidate_rows}
    if len(distinct_dates) != expected["distinct_dates"]:
        failures.append("DISTINCT_DATE_COUNT_MISMATCH")

    source_hash = sha256(source_path)
    wrong_source_hash_rows = [
        row for row in candidate_rows
        if clean(row.get("source_file_sha256")) != source_hash
    ]
    if wrong_source_hash_rows:
        failures.append("CANDIDATE_SOURCE_HASH_MISMATCH")

    invalid_price_rows = []
    for row in candidate_rows:
        try:
            if float(clean(row.get("selected_price"))) <= 0:
                invalid_price_rows.append(row)
        except ValueError:
            invalid_price_rows.append(row)
    if invalid_price_rows:
        failures.append("INVALID_SELECTED_PRICE")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    reconciliation_path = OUTPUT / "collector_august1_row_level_reconciliation.csv"
    summary_output = OUTPUT / "collector_august1_row_level_reconstruction_certification_summary.json"
    write_csv(reconciliation_path, reconciliation, ROW_FIELDS)

    summary = {
        "block_name": "Collector August 1 Row-Level Reconstruction Certification",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot_id"],
        "candidate_history_sha256": sha256(history_path),
        "certified_archive_source_sha256": source_hash,
        "candidate_rows": len(candidate_rows),
        "source_subset_rows": len(source_subset),
        "archive_backed_products": len(archive_ids),
        "governed_no_history_products": len(no_history_rows),
        "distinct_dates": len(distinct_dates),
        "duplicate_candidate_key_count": duplicate_candidate_keys,
        "duplicate_source_key_count": duplicate_source_keys,
        "missing_candidate_key_count": len(missing_candidate_keys),
        "extra_candidate_key_count": len(extra_candidate_keys),
        "row_fingerprint_mismatch_count": mismatched_rows,
        "candidate_source_hash_mismatch_count": len(wrong_source_hash_rows),
        "invalid_selected_price_count": len(invalid_price_rows),
        "row_level_reconstruction_certified": not failures,
        "historical_observation_ledger_build_authorized": not failures,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "reconciliation_sha256": sha256(reconciliation_path),
        "critical_failures": failures,
        "status": (
            "PASS_COLLECTOR_AUGUST1_ROW_LEVEL_RECONSTRUCTION_CERTIFICATION"
            if not failures
            else "FAIL_COLLECTOR_AUGUST1_ROW_LEVEL_RECONSTRUCTION_CERTIFICATION"
        ),
    }
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
