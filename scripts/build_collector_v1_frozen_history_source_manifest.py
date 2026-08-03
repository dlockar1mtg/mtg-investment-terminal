from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data/governance/permanence/certification/collector_v1_history_foundation_reproducibility/collector_history_foundation_contributing_source_inventory.csv"
LEDGER = ROOT / "data/operations/mtg_universal_history_ledger/universal_mtg_historical_observation_ledger.csv"
OUT = ROOT / "data/governance/permanence/certification/collector_v1_frozen_history_source_manifest"

DERIVED_TERMS = (
    "recommendation", "forecast", "ranking", "evaluation", "model_output",
    "full_model", "guarded", "market_value_admission", "product_registry",
    "portfolio", "owned_inventory", "positions", "signal_scores",
)
COPY_TERMS = (
    "backup", "attempt", "reclassified", "reclassification", "repair_input",
    "promotion_backups", "consolidated", "archive", "staging",
)
NONOBSERVATION_TERMS = (
    "manual_review", "product_coverage", "source_quality", "candidate_lane",
    "review_queue", "audit", "manifest", "summary",
)
CURRENT_TERMS = ("current", "latest_prices", "snapshot", "purchase_refresh")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
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


def truth(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def choose_role(row: dict[str, str]) -> tuple[str, str]:
    source_file = str(row.get("source_file", "")).replace("/", "\\")
    lower = source_file.lower()
    reasons = str(row.get("semantic_reasons", ""))

    if "secret_lair" in lower:
        return "EXCLUDED_OUT_OF_SCOPE", "SECRET_LAIR_SOURCE"
    if "pre_collector" in lower:
        return "EXCLUDED_OUT_OF_SCOPE", "PRE_COLLECTOR_SOURCE"
    if any(term in lower for term in COPY_TERMS):
        return "EXCLUDED_DERIVED_OR_OPERATIONAL", "COPY_ARCHIVE_OR_REPAIR_ARTIFACT"
    if any(term in lower for term in DERIVED_TERMS):
        return "EXCLUDED_DERIVED_OR_OPERATIONAL", "DERIVED_OR_OPERATIONAL_OUTPUT"
    if any(term in lower for term in NONOBSERVATION_TERMS):
        return "EXCLUDED_DERIVED_OR_OPERATIONAL", "NON_OBSERVATION_FILE"
    if "DERIVED_VALUATION_FIELD" in reasons or "MISSING_OBSERVATION_DATE" in reasons:
        return "EXCLUDED_DERIVED_OR_OPERATIONAL", reasons or "INVALID_OBSERVATION_SEMANTICS"
    if any(term in lower for term in CURRENT_TERMS) or "CURRENT_OR_SNAPSHOT_SOURCE" in reasons:
        return "CURRENT_PRODUCTION_ONLY", "CURRENT_OR_SNAPSHOT_SOURCE"
    if "ebay" in lower:
        return "CORROBORATING_LISTING_ONLY", "EBAY_LISTING_OR_ASKING_PRICE"
    if "tcgcsv" in lower or "tcgplayer" in lower:
        return "AUTHORITATIVE_PRICE_CANDIDATE", "TCGCSV_OR_TCGPLAYER_MARKET_OBSERVATION_CANDIDATE"
    if "daily_price_observations" in lower:
        return "FALLBACK_LOW_PRICE_ONLY", "LOW_PRICE_SERIES_REQUIRES_SEPARATE_ADJUDICATION"
    if str(row.get("semantic_state", "")) == "RAW_CANDIDATE":
        return "REVIEW_REQUIRED", "RAW_LOOKING_SOURCE_WITH_UNRESOLVED_PROVIDER_SEMANTICS"
    return "EXCLUDED_DERIVED_OR_OPERATIONAL", reasons or "UNRESOLVED_NON_RAW_SOURCE"


def ledger_source_counts() -> dict[str, dict[str, object]]:
    if not LEDGER.is_file():
        return {}
    rows = read_csv(LEDGER)
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        source_file = str(row.get("source_file", "")).replace("/", "\\")
        if not source_file:
            continue
        item = grouped.setdefault(source_file, {
            "ledger_row_count": 0,
            "ledger_products": set(),
            "ledger_dates": [],
            "ledger_price_fields": set(),
            "ledger_sources": set(),
        })
        item["ledger_row_count"] = int(item["ledger_row_count"]) + 1
        product = str(row.get("canonical_product_id", "") or row.get("tcgplayer_product_id", "")).strip()
        if product:
            item["ledger_products"].add(product)
        date = str(row.get("observation_date", "") or row.get("observed_at_utc", "")).strip()
        if date:
            item["ledger_dates"].append(date)
        price_field = str(row.get("price_field", "")).strip()
        if price_field:
            item["ledger_price_fields"].add(price_field)
        source_name = str(row.get("source_name", "")).strip()
        if source_name:
            item["ledger_sources"].add(source_name)
    return grouped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    missing = [str(path.relative_to(ROOT)) for path in (INVENTORY, LEDGER) if not path.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL_REQUIRED_INPUTS_MISSING", "missing": missing}, indent=2))
        return 1 if args.strict else 0

    inventory = read_csv(INVENTORY)
    ledger_index = ledger_source_counts()
    adjudicated: list[dict[str, object]] = []

    for row in inventory:
        source_file = str(row.get("source_file", "")).replace("/", "\\")
        source_path = ROOT / Path(source_file)
        role, reason = choose_role(row)
        ledger = ledger_index.get(source_file, {})
        dates = list(ledger.get("ledger_dates", []))
        products = set(ledger.get("ledger_products", set()))
        price_fields = set(ledger.get("ledger_price_fields", set()))
        sources = set(ledger.get("ledger_sources", set()))
        exists = source_path.is_file()
        source_hash = sha256(source_path) if exists else ""
        included = role in {
            "AUTHORITATIVE_PRICE_CANDIDATE",
            "CORROBORATING_LISTING_ONLY",
            "FALLBACK_LOW_PRICE_ONLY",
            "REVIEW_REQUIRED",
        }
        adjudicated.append({
            "source_file": source_file,
            "source_sha256": source_hash,
            "source_exists": exists,
            "source_role": role,
            "frozen_manifest_candidate": included,
            "row_count": row.get("row_count", ""),
            "distinct_product_count": row.get("distinct_product_count", ""),
            "first_observation_date": min(dates) if dates else row.get("first_observation_date", ""),
            "last_observation_date": max(dates) if dates else row.get("last_observation_date", ""),
            "ledger_row_count": ledger.get("ledger_row_count", 0),
            "ledger_distinct_product_count": len(products),
            "ledger_price_fields": "|".join(sorted(price_fields)),
            "ledger_source_names": "|".join(sorted(sources)),
            "semantic_state": row.get("semantic_state", ""),
            "semantic_reasons": row.get("semantic_reasons", ""),
            "adjudication_reason": reason,
            "historical_authority_certified": False,
        })

    fields = list(adjudicated[0].keys()) if adjudicated else []
    adjudication_path = OUT / "collector_history_source_adjudication.csv"
    write_csv(adjudication_path, adjudicated, fields)

    manifest = [row for row in adjudicated if truth(row["frozen_manifest_candidate"])]
    manifest_path = OUT / "collector_frozen_history_source_manifest.csv"
    write_csv(manifest_path, manifest, fields)

    role_counts = Counter(str(row["source_role"]) for row in adjudicated)
    critical_failures = []
    if any("secret_lair" in str(row["source_file"]).lower() for row in manifest):
        critical_failures.append("SECRET_LAIR_PRESENT_IN_FROZEN_MANIFEST")
    if any("pre_collector" in str(row["source_file"]).lower() for row in manifest):
        critical_failures.append("PRE_COLLECTOR_PRESENT_IN_FROZEN_MANIFEST")
    if any(row["source_role"] == "AUTHORITATIVE_PRICE_CANDIDATE" and "ebay" in str(row["source_file"]).lower() for row in manifest):
        critical_failures.append("EBAY_GRANTED_AUTHORITATIVE_PRICE_ROLE")
    if any(not str(row["source_sha256"]) for row in manifest):
        critical_failures.append("MANIFEST_SOURCE_HASH_MISSING")

    summary = {
        "block_name": "Collector V1 Frozen Historical Source Manifest",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reproducibility_inventory_source_count": len(inventory),
        "adjudicated_source_count": len(adjudicated),
        "frozen_manifest_candidate_count": len(manifest),
        "source_role_counts": dict(sorted(role_counts.items())),
        "authoritative_price_candidate_count": role_counts.get("AUTHORITATIVE_PRICE_CANDIDATE", 0),
        "corroborating_listing_source_count": role_counts.get("CORROBORATING_LISTING_ONLY", 0),
        "fallback_low_price_source_count": role_counts.get("FALLBACK_LOW_PRICE_ONLY", 0),
        "review_required_source_count": role_counts.get("REVIEW_REQUIRED", 0),
        "excluded_source_count": role_counts.get("EXCLUDED_OUT_OF_SCOPE", 0) + role_counts.get("EXCLUDED_DERIVED_OR_OPERATIONAL", 0),
        "current_production_only_source_count": role_counts.get("CURRENT_PRODUCTION_ONLY", 0),
        "adjudication_path": str(adjudication_path.relative_to(ROOT)),
        "adjudication_sha256": sha256(adjudication_path),
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256(manifest_path),
        "open_ended_repository_scan_authorized_for_replay": False,
        "frozen_manifest_build_certified": len(critical_failures) == 0,
        "raw_historical_price_authority_certified": False,
        "historical_coverage_assessment_authorized": False,
        "lifecycle_panel_build_authorized": False,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": critical_failures,
        "status": "PASS_COLLECTOR_V1_FROZEN_HISTORY_SOURCE_MANIFEST" if not critical_failures else "FAIL_COLLECTOR_V1_FROZEN_HISTORY_SOURCE_MANIFEST",
    }
    summary_path = OUT / "collector_frozen_history_source_manifest_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"].startswith("PASS") else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
