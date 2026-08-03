from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_identity_authority_and_reconstruction_contract_v1.json"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_august1_identity_authority_and_reconstruction"

IDENTITY_FIELDS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "release_date",
    "release_state",
    "forecast_route",
    "identity_authority_status",
    "history_classification",
]

HISTORY_FIELDS = [
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
]

COVERAGE_FIELDS = [
    "canonical_product_id",
    "tcgplayer_product_id",
    "canonical_product_name",
    "history_classification",
    "archive_observation_count",
    "first_observation_date",
    "last_observation_date",
    "forecast_route",
    "direct_history_modeling_allowed",
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


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    identity_cfg = contract["identity_authority"]
    source_cfg = contract["certified_archive_source"]
    exception_cfg = contract["governed_exception"]

    identity_path = ROOT / identity_cfg["path"]
    source_path = ROOT / source_cfg["path"]
    failures: list[str] = []

    if not identity_path.is_file():
        failures.append("IDENTITY_AUTHORITY_MISSING")
    if not source_path.is_file():
        failures.append("CERTIFIED_ARCHIVE_SOURCE_MISSING")
    if failures:
        raise SystemExit(";".join(failures))

    identity_hash = sha256(identity_path)
    source_hash = sha256(source_path)
    if identity_hash != identity_cfg["sha256"]:
        failures.append("IDENTITY_AUTHORITY_SHA256_MISMATCH")
    if source_hash != source_cfg["sha256"]:
        failures.append("ARCHIVE_SOURCE_SHA256_MISMATCH")

    identity_rows = read_csv(identity_path)
    source_rows = read_csv(source_path)

    if len(identity_rows) != identity_cfg["required_rows"]:
        failures.append("IDENTITY_AUTHORITY_ROW_COUNT_MISMATCH")

    primary_field = identity_cfg["primary_identity_field"]
    tcg_field = identity_cfg["tcgplayer_identity_field"]
    primary_ids = [clean(row.get(primary_field)) for row in identity_rows]
    tcg_ids = [clean(row.get(tcg_field)) for row in identity_rows]

    if len(set(primary_ids)) != identity_cfg["required_unique_primary_identities"] or "" in primary_ids:
        failures.append("PRIMARY_IDENTITY_UNIQUENESS_FAILURE")
    if len(set(tcg_ids)) != identity_cfg["required_unique_tcgplayer_ids"] or "" in tcg_ids:
        failures.append("TCGPLAYER_IDENTITY_UNIQUENESS_FAILURE")

    source_by_tcg: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        source_by_tcg[clean(row.get("tcgplayer_product_id"))].append(row)

    normalized_identity: list[dict[str, Any]] = []
    reconstructed: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for row in identity_rows:
        canonical_id = clean(row.get(primary_field))
        tcg_id = clean(row.get(tcg_field))
        name = clean(row.get("identity__canonical_product_name"))
        release_date = clean(row.get("identity__raw_released_on"))[:10]
        release_state = clean(row.get("identity__release_state"))
        forecast_route = clean(row.get("forecast_route"))
        archive_rows = source_by_tcg.get(tcg_id, [])

        if tcg_id == exception_cfg["tcgplayer_product_id"]:
            history_classification = exception_cfg["classification"]
            if archive_rows:
                failures.append("GOVERNED_EXCEPTION_HAS_ARCHIVE_ROWS")
            if release_date != exception_cfg["release_date"]:
                failures.append("GOVERNED_EXCEPTION_RELEASE_DATE_MISMATCH")
            if release_state != exception_cfg["release_state"]:
                failures.append("GOVERNED_EXCEPTION_RELEASE_STATE_MISMATCH")
            if forecast_route != exception_cfg["required_forecast_route"]:
                failures.append("GOVERNED_EXCEPTION_FORECAST_ROUTE_MISMATCH")
            direct_history_allowed = False
        else:
            history_classification = "CERTIFIED_TCGCSV_ARCHIVE_HISTORY"
            if not archive_rows:
                failures.append(f"ARCHIVE_HISTORY_MISSING:{tcg_id}")
            direct_history_allowed = True

        normalized_identity.append({
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": tcg_id,
            "canonical_product_name": name,
            "release_date": release_date,
            "release_state": release_state,
            "forecast_route": forecast_route,
            "identity_authority_status": clean(row.get("identity__identity_authority_status")),
            "history_classification": history_classification,
        })

        dates: list[str] = []
        for source_row in archive_rows:
            observation_date = clean(source_row.get("observation_date"))[:10]
            dates.append(observation_date)
            reconstructed.append({
                "canonical_product_id": canonical_id,
                "tcgplayer_product_id": tcg_id,
                "canonical_product_name": name,
                "observation_date": observation_date,
                "market_price": clean(source_row.get("market_price")),
                "low_price": clean(source_row.get("low_price")),
                "mid_price": clean(source_row.get("mid_price")),
                "high_price": clean(source_row.get("high_price")),
                "direct_low_price": clean(source_row.get("direct_low_price")),
                "selected_price": clean(source_row.get("selected_price")),
                "selection_method": clean(source_row.get("selection_method")),
                "price_data_quality": clean(source_row.get("price_data_quality")),
                "source_name": "TCGCSV_ARCHIVE_CERTIFIED",
                "source_file_sha256": source_hash,
            })

        coverage.append({
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": tcg_id,
            "canonical_product_name": name,
            "history_classification": history_classification,
            "archive_observation_count": len(archive_rows),
            "first_observation_date": min(dates) if dates else "",
            "last_observation_date": max(dates) if dates else "",
            "forecast_route": forecast_route,
            "direct_history_modeling_allowed": direct_history_allowed,
        })

    archive_backed = [row for row in coverage if row["history_classification"] == "CERTIFIED_TCGCSV_ARCHIVE_HISTORY"]
    no_history = [row for row in coverage if row["history_classification"] == exception_cfg["classification"]]

    if len(archive_backed) != source_cfg["required_archive_backed_products"]:
        failures.append("ARCHIVE_BACKED_PRODUCT_COUNT_MISMATCH")
    if len(no_history) != source_cfg["required_no_history_products"]:
        failures.append("NO_HISTORY_PRODUCT_COUNT_MISMATCH")

    duplicate_keys = Counter(
        (row["canonical_product_id"], row["observation_date"])
        for row in reconstructed
    )
    duplicate_key_count = sum(1 for count in duplicate_keys.values() if count > 1)
    if duplicate_key_count:
        failures.append("DUPLICATE_RECONSTRUCTED_PRODUCT_DATE_KEYS")

    invalid_prices = [
        row for row in reconstructed
        if not clean(row["selected_price"]) or float(row["selected_price"]) <= 0
    ]
    if invalid_prices:
        failures.append("INVALID_RECONSTRUCTED_SELECTED_PRICE")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    identity_output = OUTPUT / "collector_august1_identity_authority.csv"
    history_output = OUTPUT / "collector_august1_reconstructed_history_candidate.csv"
    coverage_output = OUTPUT / "collector_august1_reconstruction_coverage.csv"
    summary_output = OUTPUT / "collector_august1_identity_authority_and_reconstruction_summary.json"

    write_csv(identity_output, normalized_identity, IDENTITY_FIELDS)
    write_csv(history_output, reconstructed, HISTORY_FIELDS)
    write_csv(coverage_output, coverage, COVERAGE_FIELDS)

    summary = {
        "block_name": "Collector August 1 Identity Authority and Reconstruction",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governing_snapshot_id": contract["governing_snapshot"]["snapshot_id"],
        "governing_product_count": contract["governing_snapshot"]["certified_product_count"],
        "identity_authority_path": identity_cfg["path"],
        "identity_authority_sha256": identity_hash,
        "archive_source_path": source_cfg["path"],
        "archive_source_sha256": source_hash,
        "identity_rows": len(normalized_identity),
        "archive_backed_products": len(archive_backed),
        "governed_no_history_products": len(no_history),
        "reconstructed_history_rows": len(reconstructed),
        "distinct_reconstructed_products": len({row["canonical_product_id"] for row in reconstructed}),
        "distinct_reconstructed_dates": len({row["observation_date"] for row in reconstructed}),
        "duplicate_product_date_key_count": duplicate_key_count,
        "invalid_selected_price_count": len(invalid_prices),
        "governed_exception_tcgplayer_product_id": exception_cfg["tcgplayer_product_id"],
        "governed_exception_classification": exception_cfg["classification"],
        "identity_authority_certified": not failures,
        "reconstruction_candidate_built": not failures,
        "row_level_reconstruction_certification_authorized": not failures,
        "historical_observation_ledger_build_authorized": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "identity_output_sha256": sha256(identity_output),
        "history_output_sha256": sha256(history_output),
        "coverage_output_sha256": sha256(coverage_output),
        "critical_failures": failures,
        "status": (
            "PASS_COLLECTOR_AUGUST1_IDENTITY_AUTHORITY_AND_RECONSTRUCTION"
            if not failures
            else "FAIL_COLLECTOR_AUGUST1_IDENTITY_AUTHORITY_AND_RECONSTRUCTION"
        ),
    }
    summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
