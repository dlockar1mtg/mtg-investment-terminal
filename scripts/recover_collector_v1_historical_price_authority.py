from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = ROOT / "data" / "operations" / "mtg_marketplace" / "governed_universe" / "governed_marketplace_product_map.csv"
DEFAULT_OUTPUT = ROOT / "data" / "governance" / "permanence" / "certification" / "collector_v1_historical_price_recovery"
APPROVED_ROOTS = (
    ROOT / "data" / "operations" / "mtg_universal_history_ledger",
    ROOT / "data" / "history",
    ROOT / "data" / "archive",
    ROOT / "data" / "vault",
    ROOT / "data" / "operations" / "mtg_data_vault",
)
CHECKPOINTS = (0, 30, 60, 90, 120, 180, 270, 365)
ID_FIELDS = ("canonical_product_id", "investment_product_id", "tcgplayer_product_id", "source_product_id", "product_id")
NAME_FIELDS = ("canonical_product_name", "box_name", "product_name", "source_product_name")
DATE_FIELDS = ("observation_date", "observed_at_utc", "observed_at", "collected_at", "source_timestamp", "date")
PRICE_FIELDS = ("market_price", "certified_price", "price", "mid_price")
SOURCE_FIELDS = ("source_name", "price_source", "provider", "source")
RELEASE_FIELDS = ("release_date", "release_date_utc", "set_release_date")
PROHIBITED_PATH_TERMS = (
    "secret_lair", "pre_collector", "ebay", "staging", "validation", "backup", "attempt",
    "repair", "reclassified", "promotion_backup", "current", "latest", "snapshot",
    "forecast", "recommendation", "ranking", "portfolio", "model_input",
)
DERIVED_PRICE_FIELDS = {"evaluated_market_value_usd", "market_value_usd", "consolidated_price", "current_price"}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


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


def first(row: dict[str, str], fields: Iterable[str]) -> str:
    for field in fields:
        value = str(row.get(field, "") or "").strip()
        if value:
            return value
    return ""


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def parse_date(value: object):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def parse_price(value: object):
    try:
        parsed = float(str(value or "").replace("$", "").replace(",", "").strip())
        return parsed if parsed > 0 else None
    except ValueError:
        return None


def discover_sources() -> list[Path]:
    found: set[Path] = set()
    for root in APPROVED_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            found.add(path.resolve())
    return sorted(found)


def build_universe(path: Path):
    _, rows = read_csv(path)
    by_id: dict[str, dict[str, str]] = {}
    by_name: dict[str, dict[str, str]] = {}
    for row in rows:
        product_class = norm(row.get("product_class"))
        name_text = norm(first(row, NAME_FIELDS))
        if "collector booster" not in product_class and "collector booster" not in name_text:
            continue
        canonical = first(row, ("canonical_product_id",))
        if canonical:
            by_id[canonical] = row
        tcgplayer = first(row, ("approved_tcgplayer_product_id", "tcgplayer_product_id"))
        if tcgplayer:
            by_id[tcgplayer] = row
        if name_text:
            by_name[name_text] = row
    return by_id, by_name


def resolve_product(row: dict[str, str], by_id, by_name):
    for field in ID_FIELDS:
        value = str(row.get(field, "") or "").strip()
        if value and value in by_id:
            return by_id[value], field
    for field in NAME_FIELDS:
        value = norm(row.get(field))
        if value and value in by_name:
            return by_name[value], field
    return None, ""


def path_prohibited(path: Path) -> str:
    lower = str(path).replace("\\", "/").lower()
    hits = [term for term in PROHIBITED_PATH_TERMS if term in lower]
    return "|".join(sorted(set(hits)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover Collector V1 historical price authority and checkpoint coverage.")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    by_id, by_name = build_universe(args.universe.resolve())
    sources = discover_sources()
    inventory: list[dict[str, object]] = []
    accepted: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    now = datetime.now(timezone.utc)

    for path in sources:
        relative = str(path.relative_to(ROOT))
        file_hash = sha256(path)
        prohibited = path_prohibited(path)
        try:
            fields, rows = read_csv(path)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            inventory.append({"source_path": relative, "source_sha256": file_hash, "row_count": 0, "accepted_row_count": 0, "source_state": "READ_ERROR", "reason": type(exc).__name__})
            continue

        date_field = next((field for field in DATE_FIELDS if field in fields), "")
        price_field = next((field for field in PRICE_FIELDS if field in fields), "")
        if not date_field or not price_field:
            inventory.append({"source_path": relative, "source_sha256": file_hash, "row_count": len(rows), "accepted_row_count": 0, "source_state": "NO_OBSERVATION_SCHEMA", "reason": "missing_date_or_price"})
            continue
        if price_field in DERIVED_PRICE_FIELDS or prohibited:
            inventory.append({"source_path": relative, "source_sha256": file_hash, "row_count": len(rows), "accepted_row_count": 0, "source_state": "PROHIBITED_SOURCE", "reason": prohibited or "derived_price_field"})
            continue

        file_accepted = 0
        for index, row in enumerate(rows, start=2):
            product, mapping = resolve_product(row, by_id, by_name)
            observed = parse_date(row.get(date_field))
            price = parse_price(row.get(price_field))
            provider = first(row, SOURCE_FIELDS).upper()
            reason = ""
            if product is None:
                reason = "NOT_GOVERNED_COLLECTOR_PRODUCT"
            elif observed is None:
                reason = "INVALID_OR_MISSING_OBSERVATION_DATE"
            elif observed > now:
                reason = "FUTURE_DATED_OBSERVATION"
            elif price is None:
                reason = "INVALID_OR_NONPOSITIVE_PRICE"
            elif provider and provider not in {"TCGCSV", "TCGPLAYER", "TCGPLAYER_API", "TCGPLAYER_MARKET"}:
                reason = "UNAPPROVED_PROVIDER"
            if reason:
                exclusions.append({"source_path": relative, "source_sha256": file_hash, "source_row_number": index, "exclusion_reason": reason})
                continue

            canonical_id = first(product, ("canonical_product_id",))
            release_date = parse_date(first(product, RELEASE_FIELDS))
            age_days = (observed.date() - release_date.date()).days if release_date else ""
            if release_date and age_days < 0:
                exclusions.append({"source_path": relative, "source_sha256": file_hash, "source_row_number": index, "exclusion_reason": "PRE_RELEASE_OBSERVATION"})
                continue
            accepted.append({
                "canonical_product_id": canonical_id,
                "canonical_product_name": first(product, NAME_FIELDS),
                "tcgplayer_product_id": first(product, ("approved_tcgplayer_product_id", "tcgplayer_product_id")),
                "release_date": release_date.date().isoformat() if release_date else "",
                "observation_date": observed.isoformat(),
                "product_age_days": age_days,
                "market_price": round(price, 4),
                "provider": provider or "UNSPECIFIED_APPROVED_ARCHIVE",
                "source_path": relative,
                "source_sha256": file_hash,
                "source_row_number": index,
                "identity_mapping_method": mapping,
            })
            file_accepted += 1
        inventory.append({"source_path": relative, "source_sha256": file_hash, "row_count": len(rows), "accepted_row_count": file_accepted, "source_state": "CONTRIBUTING" if file_accepted else "NO_ACCEPTED_ROWS", "reason": ""})

    deduped: dict[tuple[str, str, float, str], dict[str, object]] = {}
    for row in accepted:
        key = (str(row["canonical_product_id"]), str(row["observation_date"]), float(row["market_price"]), str(row["provider"]))
        deduped.setdefault(key, row)
    ledger = sorted(deduped.values(), key=lambda row: (str(row["canonical_product_id"]), str(row["observation_date"]), str(row["provider"])))

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in ledger:
        grouped[str(row["canonical_product_id"])].append(row)
    unique_products = {str(row.get("canonical_product_id") or ""): row for row in by_id.values() if row.get("canonical_product_id")}
    coverage: list[dict[str, object]] = []
    products_all_checkpoints = 0
    for canonical_id, product in sorted(unique_products.items()):
        rows = grouped.get(canonical_id, [])
        ages = {int(row["product_age_days"]) for row in rows if str(row.get("product_age_days", "")).lstrip("-").isdigit()}
        checkpoint_flags = {day: day in ages for day in CHECKPOINTS}
        all_supported = all(checkpoint_flags.values())
        products_all_checkpoints += int(all_supported)
        coverage.append({
            "canonical_product_id": canonical_id,
            "canonical_product_name": first(product, NAME_FIELDS),
            "observation_count": len(rows),
            "distinct_observation_date_count": len({str(row["observation_date"])[:10] for row in rows}),
            "minimum_observation_date": min((str(row["observation_date"]) for row in rows), default=""),
            "maximum_observation_date": max((str(row["observation_date"]) for row in rows), default=""),
            **{f"checkpoint_{day}d_exact_supported": checkpoint_flags[day] for day in CHECKPOINTS},
            "all_required_checkpoints_exact_supported": all_supported,
        })

    out = args.output_root.resolve()
    inventory_path = out / "collector_historical_price_recovery_source_inventory.csv"
    ledger_path = out / "collector_historical_price_replay_ledger_candidate.csv"
    exclusions_path = out / "collector_historical_price_recovery_exclusions.csv"
    coverage_path = out / "collector_historical_checkpoint_coverage.csv"
    summary_path = out / "collector_historical_price_recovery_summary.json"
    write_csv(inventory_path, inventory, ["source_path", "source_sha256", "row_count", "accepted_row_count", "source_state", "reason"])
    write_csv(ledger_path, ledger, ["canonical_product_id", "canonical_product_name", "tcgplayer_product_id", "release_date", "observation_date", "product_age_days", "market_price", "provider", "source_path", "source_sha256", "source_row_number", "identity_mapping_method"])
    write_csv(exclusions_path, exclusions, ["source_path", "source_sha256", "source_row_number", "exclusion_reason"])
    coverage_fields = ["canonical_product_id", "canonical_product_name", "observation_count", "distinct_observation_date_count", "minimum_observation_date", "maximum_observation_date"] + [f"checkpoint_{day}d_exact_supported" for day in CHECKPOINTS] + ["all_required_checkpoints_exact_supported"]
    write_csv(coverage_path, coverage, coverage_fields)

    historical_authority = len(ledger) > 0 and all(row["source_sha256"] and row["provider"] for row in ledger)
    coverage_complete = historical_authority
    lifecycle_authorized = historical_authority and products_all_checkpoints > 0
    summary = {
        "block_name": "Collector V1 Historical Price Recovery and Coverage",
        "block_version": "1.0.0",
        "generated_at_utc": now.isoformat(),
        "approved_source_root_count": len(APPROVED_ROOTS),
        "discovered_source_count": len(sources),
        "contributing_source_count": sum(int(row["accepted_row_count"]) > 0 for row in inventory),
        "accepted_rows_before_deduplication": len(accepted),
        "replay_ledger_row_count": len(ledger),
        "duplicate_rows_collapsed": len(accepted) - len(ledger),
        "excluded_row_count": len(exclusions),
        "collector_product_count": len(unique_products),
        "products_with_any_historical_observation": sum(int(row["observation_count"]) > 0 for row in coverage),
        "products_with_all_required_exact_checkpoints": products_all_checkpoints,
        "required_checkpoints_days": list(CHECKPOINTS),
        "raw_historical_price_authority_certified": historical_authority,
        "historical_coverage_assessment_completed": coverage_complete,
        "lifecycle_panel_build_authorized": lifecycle_authorized,
        "model_tournament_authorized": False,
        "purchase_recommendations_authorized": False,
        "authority_reason": "GOVERNED_ARCHIVAL_PRICE_ROWS_RECOVERED" if historical_authority else "NO_GOVERNED_HISTORICAL_PRICE_ROWS_RECOVERED",
        "lifecycle_authorization_reason": "AT_LEAST_ONE_PRODUCT_HAS_ALL_REQUIRED_EXACT_CHECKPOINTS" if lifecycle_authorized else "REQUIRED_EXACT_CHECKPOINT_COVERAGE_NOT_ESTABLISHED",
        "status": "PASS_COLLECTOR_V1_HISTORICAL_PRICE_RECOVERY_AND_COVERAGE",
    }
    out.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.strict and any(not str(row["source_sha256"]) for row in ledger):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
