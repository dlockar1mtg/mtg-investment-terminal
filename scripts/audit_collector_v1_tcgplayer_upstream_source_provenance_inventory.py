from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "collector-20260801T211201Z-7688afbd"
OPERATING_DATE = "2026-08-01"
TIMEZONE = "America/Chicago"
BUNDLE_SHA = "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
PRODUCT_COUNT = 50
PREREQUISITE = ROOT / "data/governance/permanence/certification/collector_v1_tcgplayer_history_lineage_and_reproducibility/collector_tcgplayer_history_lineage_and_reproducibility_summary.json"
OBSERVATION_LEDGER = ROOT / "data/operations/mtg_universal_history_ledger/universal_mtg_historical_observation_ledger.csv"
DAILY_LEDGER = ROOT / "data/operations/mtg_universal_history_ledger/universal_mtg_daily_consolidated_ledger.csv"
REGISTRY = ROOT / "data/validation/phase_10/unified_mtg_registry/unified_mtg_product_registry.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_tcgplayer_upstream_source_provenance_inventory"

ALLOWED = {
    "CANDIDATE_RAW_TCGPLAYER_HISTORY_SOURCE",
    "CANDIDATE_REPRODUCIBLE_TCGPLAYER_HISTORY_SOURCE",
    "DERIVED_SOURCE_NOT_AUTHORITY",
    "LISTING_OR_SUPPLY_SOURCE_NOT_PRICE_AUTHORITY",
    "REFERENCED_SOURCE_FILE_MISSING",
    "UNRESOLVED_SOURCE_REFERENCE",
}


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


def resolve_reference(value: str) -> tuple[str, Path | None]:
    text = clean(value).replace("\\", "/")
    if not text:
        return "", None
    candidate = Path(text)
    if candidate.is_absolute():
        return text, candidate
    return text, ROOT / candidate


def classify(source_name: str, source_file: str, resolved: Path | None) -> tuple[str, str]:
    combined = f"{source_name}|{source_file}".upper()
    if any(term in combined for term in ("EBAY", "ASKING", "LISTING", "SUPPLY")):
        return "LISTING_OR_SUPPLY_SOURCE_NOT_PRICE_AUTHORITY", "LISTING_SUPPLY_SEMANTICS"
    if not source_file:
        return "UNRESOLVED_SOURCE_REFERENCE", "SOURCE_FILE_BLANK"
    if resolved is None or not resolved.is_file():
        return "REFERENCED_SOURCE_FILE_MISSING", "REFERENCED_PATH_NOT_FOUND"
    suffix = resolved.suffix.lower()
    if any(term in combined for term in ("CONSOLIDATED", "CANONICAL", "MODEL_INPUT", "CERTIFICATION", "OUTPUT")):
        return "DERIVED_SOURCE_NOT_AUTHORITY", "DERIVED_OR_CERTIFICATION_ARTIFACT"
    if "TCG" in combined or "TCGPLAYER" in combined or "TCGCSV" in combined:
        if suffix in {".csv", ".json", ".jsonl", ".parquet"}:
            return "CANDIDATE_RAW_TCGPLAYER_HISTORY_SOURCE", "TCGPLAYER_NAMED_EXISTING_DATA_FILE"
        if suffix == ".py":
            return "CANDIDATE_REPRODUCIBLE_TCGPLAYER_HISTORY_SOURCE", "TCGPLAYER_NAMED_ACTIVE_CODE_FILE"
    return "UNRESOLVED_SOURCE_REFERENCE", "EXISTING_FILE_WITH_UNPROVEN_SEMANTICS"


def main() -> int:
    failures: list[str] = []
    required = [PREREQUISITE, OBSERVATION_LEDGER, DAILY_LEDGER, REGISTRY]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print(json.dumps({"status": "BLOCKED_REQUIRED_INPUT_MISSING", "missing": missing}, indent=2))
        return 2

    prerequisite = json.loads(PREREQUISITE.read_text(encoding="utf-8-sig"))
    if prerequisite.get("status") != "PASS_COLLECTOR_TCGPLAYER_HISTORY_LINEAGE_AND_REPRODUCIBILITY":
        failures.append("LINEAGE_PREREQUISITE_INVALID")
    if prerequisite.get("governing_snapshot_id") != SNAPSHOT_ID:
        failures.append("SNAPSHOT_ID_MISMATCH")
    if prerequisite.get("governing_certified_product_count") != PRODUCT_COUNT:
        failures.append("PRODUCT_COUNT_MISMATCH")
    if prerequisite.get("raw_historical_price_authority_certified") is not False:
        failures.append("PREREQUISITE_AUTHORITY_BOUNDARY_INVALID")

    ledger = read_csv(OBSERVATION_LEDGER)
    registry = read_csv(REGISTRY)
    registry_aliases: set[str] = set()
    for row in registry:
        for field in ("universal_mtg_product_id", "source_product_id", "tcgplayer_product_id"):
            value = clean(row.get(field))
            if value:
                registry_aliases.add(value)
                if field == "tcgplayer_product_id":
                    registry_aliases.add(f"MTG-CANON-TCGPLAYER-{value}")

    source_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in ledger:
        source_groups[(clean(row.get("source_name")), clean(row.get("source_file")))].append(row)

    source_inventory: list[dict[str, Any]] = []
    classification_counts: Counter[str] = Counter()
    for (source_name, source_file), rows in sorted(source_groups.items()):
        reference_text, resolved = resolve_reference(source_file)
        classification, reason = classify(source_name, source_file, resolved)
        classification_counts[classification] += 1
        dates = {clean(row.get("observation_date")) for row in rows if clean(row.get("observation_date"))}
        ids = {clean(row.get("canonical_product_id")) for row in rows if clean(row.get("canonical_product_id"))}
        mapped_ids = {value for value in ids if value in registry_aliases}
        price_fields = sorted({field for field in ("market_price", "low_price", "price", "current_price") if any(clean(row.get(field)) for row in rows)})
        source_inventory.append({
            "source_name": source_name,
            "source_file": source_file,
            "resolved_path": reference_text,
            "reference_exists": bool(resolved and resolved.is_file()),
            "sha256": sha256(resolved) if resolved and resolved.is_file() else "",
            "ledger_row_count": len(rows),
            "distinct_observation_dates": len(dates),
            "first_observation_date": min(dates) if dates else "",
            "last_observation_date": max(dates) if dates else "",
            "distinct_ledger_identities": len(ids),
            "mapped_registry_identities": len(mapped_ids),
            "price_fields_present": "|".join(price_fields),
            "candidate_classification": classification,
            "classification_reason": reason,
            "raw_source_certification_authorized": False,
            "ledger_admission_authorized": False,
        })

    semantic_counts: Counter[tuple[str, str, str]] = Counter()
    for row in ledger:
        source_name = clean(row.get("source_name"))
        source_file = clean(row.get("source_file"))
        price_field = clean(row.get("price_field"))
        semantic_counts[(source_name, source_file, price_field)] += 1
    semantic_profile = [
        {"source_name": key[0], "source_file": key[1], "price_field": key[2], "row_count": count}
        for key, count in sorted(semantic_counts.items())
    ]

    identity_counts: dict[str, dict[str, Any]] = {}
    for row in ledger:
        identity = clean(row.get("canonical_product_id"))
        if not identity:
            continue
        record = identity_counts.setdefault(identity, {"dates": set(), "sources": set(), "rows": 0})
        record["rows"] += 1
        date = clean(row.get("observation_date"))
        if date:
            record["dates"].add(date)
        source = clean(row.get("source_name"))
        if source:
            record["sources"].add(source)
    identity_coverage = [
        {
            "canonical_product_id": identity,
            "ledger_rows": values["rows"],
            "distinct_observation_dates": len(values["dates"]),
            "source_names": "|".join(sorted(values["sources"])),
            "maps_to_unified_registry": identity in registry_aliases,
        }
        for identity, values in sorted(identity_counts.items())
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    source_path = OUT / "collector_tcgplayer_upstream_source_inventory.csv"
    semantic_path = OUT / "collector_tcgplayer_ledger_semantic_profile.csv"
    identity_path = OUT / "collector_tcgplayer_identity_coverage.csv"
    write_csv(source_path, source_inventory, list(source_inventory[0]) if source_inventory else [])
    write_csv(semantic_path, semantic_profile, ["source_name", "source_file", "price_field", "row_count"])
    write_csv(identity_path, identity_coverage, ["canonical_product_id", "ledger_rows", "distinct_observation_dates", "source_names", "maps_to_unified_registry"])

    invalid_classes = [row for row in source_inventory if row["candidate_classification"] not in ALLOWED]
    if invalid_classes:
        failures.append("INVALID_SOURCE_CLASSIFICATION")

    candidate_existing = sum(row["candidate_classification"] == "CANDIDATE_RAW_TCGPLAYER_HISTORY_SOURCE" for row in source_inventory)
    unresolved = sum(row["candidate_classification"] in {"REFERENCED_SOURCE_FILE_MISSING", "UNRESOLVED_SOURCE_REFERENCE"} for row in source_inventory)
    mapped_identity_count = sum(bool(row["maps_to_unified_registry"]) for row in identity_coverage)

    summary = {
        "block_name": "Collector TCGplayer Upstream Source Provenance Inventory",
        "block_version": "1.0.0",
        "governing_snapshot_id": SNAPSHOT_ID,
        "governing_operating_date": OPERATING_DATE,
        "governing_timezone": TIMEZONE,
        "governing_source_bundle_sha256": BUNDLE_SHA,
        "governing_certified_product_count": PRODUCT_COUNT,
        "observation_ledger_rows": len(ledger),
        "source_reference_count": len(source_inventory),
        "candidate_raw_tcgplayer_source_count": candidate_existing,
        "unresolved_or_missing_source_reference_count": unresolved,
        "ledger_identity_count": len(identity_coverage),
        "mapped_registry_identity_count": mapped_identity_count,
        "candidate_classification_counts": dict(sorted(classification_counts.items())),
        "upstream_source_provenance_inventory_completed": not failures,
        "raw_source_certification_authorized": False,
        "historical_reconstruction_execution_authorized": False,
        "historical_observation_ledger_build_authorized": False,
        "raw_historical_price_authority_certified": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "production_forecasting_authorized": False,
        "uip_delivery_authorized": False,
        "purchase_recommendations_authorized": False,
        "source_inventory_path": str(source_path.relative_to(ROOT)),
        "source_inventory_sha256": sha256(source_path),
        "semantic_profile_path": str(semantic_path.relative_to(ROOT)),
        "semantic_profile_sha256": sha256(semantic_path),
        "identity_coverage_path": str(identity_path.relative_to(ROOT)),
        "identity_coverage_sha256": sha256(identity_path),
        "critical_failures": sorted(set(failures)),
        "status": "PASS_COLLECTOR_TCGPLAYER_UPSTREAM_SOURCE_PROVENANCE_INVENTORY" if not failures else "FAIL_COLLECTOR_TCGPLAYER_UPSTREAM_SOURCE_PROVENANCE_INVENTORY",
    }
    (OUT / "collector_tcgplayer_upstream_source_provenance_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 5


if __name__ == "__main__":
    raise SystemExit(main())
