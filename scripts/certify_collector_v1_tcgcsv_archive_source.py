from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_tcgcsv_archive_source_certification_contract_v1.json"
SOURCE = ROOT / "data/operations/mtg_universal_history_completion/archive/universal_tcgcsv_monthly_archive_observations.csv"
LEDGER = ROOT / "data/operations/mtg_universal_history_ledger/universal_mtg_historical_observation_ledger.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_tcgcsv_archive_source_certification"


def clean(value: Any) -> str:
    return str(value or "").strip()


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
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def positive_number(value: Any) -> float | None:
    try:
        parsed = float(clean(value))
    except ValueError:
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def valid_date(value: Any) -> str:
    text = clean(value)[:10]
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return ""
    return text


def main() -> int:
    failures: list[str] = []
    if not CONTRACT.is_file() or not SOURCE.is_file() or not LEDGER.is_file():
        missing = [str(path.relative_to(ROOT)) for path in (CONTRACT, SOURCE, LEDGER) if not path.is_file()]
        print(json.dumps({"status": "BLOCKED_REQUIRED_INPUT_MISSING", "missing": missing}, indent=2))
        return 2

    contract = json.loads(CONTRACT.read_text(encoding="utf-8-sig"))
    expected = contract["candidate_source"]
    source_rows = read_csv(SOURCE)
    ledger_rows = [
        row for row in read_csv(LEDGER)
        if clean(row.get("source_name")) == "TCGCSV_ARCHIVE"
        and clean(row.get("source_file")) == SOURCE.name
    ]

    actual_hash = sha256(SOURCE)
    if actual_hash != expected["expected_sha256"]:
        failures.append("SOURCE_SHA256_MISMATCH")
    if len(source_rows) != int(expected["expected_rows"]):
        failures.append("SOURCE_ROW_COUNT_MISMATCH")
    if len(ledger_rows) != int(expected["expected_rows"]):
        failures.append("LEDGER_SUBSET_ROW_COUNT_MISMATCH")

    required_fields = {
        "observation_id", "observation_date", "universal_mtg_product_id",
        "tcgplayer_product_id", "market_price", "low_price", "mid_price",
        "selected_price", "selection_method", "source_name",
    }
    fields = set(source_rows[0]) if source_rows else set()
    missing_fields = sorted(required_fields - fields)
    if missing_fields:
        failures.append("REQUIRED_SOURCE_FIELDS_MISSING")

    dates: set[str] = set()
    identities: set[str] = set()
    tcgplayer_ids: set[str] = set()
    keys: list[tuple[str, str]] = []
    invalid_rows: list[dict[str, Any]] = []
    selection_counts: Counter[str] = Counter()
    market_price_rows = 0
    market_preference_violations = 0

    for index, row in enumerate(source_rows, start=2):
        date = valid_date(row.get("observation_date"))
        identity = clean(row.get("universal_mtg_product_id"))
        tcgplayer_id = clean(row.get("tcgplayer_product_id"))
        selected = positive_number(row.get("selected_price"))
        market = positive_number(row.get("market_price"))
        method = clean(row.get("selection_method"))
        source_name = clean(row.get("source_name"))
        reasons: list[str] = []

        if not date:
            reasons.append("INVALID_OBSERVATION_DATE")
        if not identity:
            reasons.append("BLANK_UNIVERSAL_IDENTITY")
        if not tcgplayer_id:
            reasons.append("BLANK_TCGPLAYER_PRODUCT_ID")
        if selected is None:
            reasons.append("NONPOSITIVE_SELECTED_PRICE")
        if source_name != "tcgcsv_archive_monthly":
            reasons.append("INVALID_SOURCE_NAME")
        if market is not None:
            market_price_rows += 1
            if method != "market_price" or selected != market:
                market_preference_violations += 1
                reasons.append("MARKET_PRICE_NOT_PREFERRED")
        elif method not in {"mid_price", "low_price"}:
            reasons.append("INVALID_FALLBACK_SELECTION_METHOD")

        if date:
            dates.add(date)
        if identity:
            identities.add(identity)
        if tcgplayer_id:
            tcgplayer_ids.add(tcgplayer_id)
        if date and identity:
            keys.append((identity, date))
        selection_counts[method] += 1

        if reasons:
            invalid_rows.append({
                "row_number": index,
                "universal_mtg_product_id": identity,
                "tcgplayer_product_id": tcgplayer_id,
                "observation_date": clean(row.get("observation_date")),
                "selected_price": clean(row.get("selected_price")),
                "selection_method": method,
                "reasons": "|".join(reasons),
            })

    duplicate_key_count = len(keys) - len(set(keys))
    if duplicate_key_count:
        failures.append("DUPLICATE_PRODUCT_DATE_KEYS")
    if invalid_rows:
        failures.append("INVALID_SOURCE_ROWS")
    if market_preference_violations:
        failures.append("MARKET_PRICE_PREFERENCE_VIOLATIONS")
    if len(dates) != int(expected["expected_distinct_dates"]):
        failures.append("DISTINCT_DATE_COUNT_MISMATCH")
    if dates and min(dates) != expected["expected_first_date"]:
        failures.append("FIRST_DATE_MISMATCH")
    if dates and max(dates) != expected["expected_last_date"]:
        failures.append("LAST_DATE_MISMATCH")
    if len(identities) != int(expected["expected_distinct_identities"]):
        failures.append("IDENTITY_COUNT_MISMATCH")

    source_fingerprints = {
        (
            clean(row.get("universal_mtg_product_id")),
            valid_date(row.get("observation_date")),
            clean(row.get("selected_price")),
            clean(row.get("tcgplayer_product_id")),
        )
        for row in source_rows
    }
    ledger_fingerprints = {
        (
            clean(row.get("canonical_product_id")),
            valid_date(row.get("observation_date")),
            clean(row.get("market_price")),
            clean(row.get("tcgplayer_product_id")),
        )
        for row in ledger_rows
    }
    unmatched_source = source_fingerprints - ledger_fingerprints
    unmatched_ledger = ledger_fingerprints - source_fingerprints
    if unmatched_source or unmatched_ledger:
        failures.append("LEDGER_SUBSET_RECONCILIATION_MISMATCH")

    OUT.mkdir(parents=True, exist_ok=True)
    invalid_path = OUT / "collector_tcgcsv_archive_invalid_rows.csv"
    write_csv(
        invalid_path,
        invalid_rows,
        ["row_number", "universal_mtg_product_id", "tcgplayer_product_id", "observation_date", "selected_price", "selection_method", "reasons"],
    )

    profile_rows = [
        {"selection_method": method, "row_count": count}
        for method, count in sorted(selection_counts.items())
    ]
    profile_path = OUT / "collector_tcgcsv_archive_selection_profile.csv"
    write_csv(profile_path, profile_rows, ["selection_method", "row_count"])

    failures = sorted(set(failures))
    summary = {
        "block_name": "Collector TCGCSV Archive Source Certification",
        "block_version": "1.0.0",
        "governing_snapshot_id": contract["governing_snapshot"]["snapshot_id"],
        "governing_operating_date": contract["governing_snapshot"]["operating_date"],
        "governing_timezone": contract["governing_snapshot"]["timezone"],
        "governing_source_bundle_sha256": contract["governing_snapshot"]["source_bundle_sha256"],
        "governing_certified_product_count": contract["governing_snapshot"]["certified_product_count"],
        "candidate_source_path": str(SOURCE.relative_to(ROOT)),
        "candidate_source_sha256": actual_hash,
        "source_rows": len(source_rows),
        "ledger_subset_rows": len(ledger_rows),
        "distinct_observation_dates": len(dates),
        "first_observation_date": min(dates) if dates else "",
        "last_observation_date": max(dates) if dates else "",
        "distinct_source_identities": len(identities),
        "distinct_tcgplayer_product_ids": len(tcgplayer_ids),
        "duplicate_product_date_key_count": duplicate_key_count,
        "invalid_source_row_count": len(invalid_rows),
        "market_price_row_count": market_price_rows,
        "market_price_preference_violation_count": market_preference_violations,
        "unmatched_source_fingerprint_count": len(unmatched_source),
        "unmatched_ledger_fingerprint_count": len(unmatched_ledger),
        "selection_method_counts": dict(sorted(selection_counts.items())),
        "raw_tcgcsv_archive_source_certified": not failures,
        "governed_historical_reconstruction_authorized": not failures,
        "historical_observation_ledger_build_authorized": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "invalid_rows_path": str(invalid_path.relative_to(ROOT)),
        "invalid_rows_sha256": sha256(invalid_path),
        "selection_profile_path": str(profile_path.relative_to(ROOT)),
        "selection_profile_sha256": sha256(profile_path),
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_TCGCSV_ARCHIVE_SOURCE_CERTIFICATION" if not failures else "FAIL_COLLECTOR_TCGCSV_ARCHIVE_SOURCE_CERTIFICATION",
    }
    summary_path = OUT / "collector_tcgcsv_archive_source_certification_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 5


if __name__ == "__main__":
    raise SystemExit(main())
