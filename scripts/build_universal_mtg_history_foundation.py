from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = (
    ROOT / "data" / "operations" / "mtg_marketplace"
    / "governed_universe" / "governed_marketplace_product_map.csv"
)
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_history_foundation"
SCAN_ROOTS = (
    ROOT / "data" / "product_master",
    ROOT / "data" / "history",
    ROOT / "data" / "staging",
    ROOT / "data" / "validation",
    ROOT / "data" / "reference" / "phase_11" / "mtg_hosted_baseline",
    ROOT / "data" / "operations" / "mtg_marketplace",
)

ID_FIELDS = ("canonical_product_id", "investment_product_id", "source_product_id")
TCGPLAYER_FIELDS = (
    "approved_tcgplayer_product_id",
    "tcgplayer_product_id",
    "tcgplayer_product_id_str",
)
NAME_FIELDS = (
    "canonical_product_name",
    "box_name",
    "box_name_master",
    "product_name",
    "source_product_name",
    "official_product_name",
)
DATE_FIELDS = (
    "observation_date", "observed_at_utc", "observed_at", "collected_at",
    "source_timestamp", "snapshot_date", "latest_observation_date",
    "last_price_checked", "date",
)
PRICE_FIELDS = (
    "market_price", "certified_price", "consolidated_price", "current_price",
    "current_price_db", "current_price_history", "evaluated_market_value_usd",
    "market_value_usd", "median_accepted_landed_price", "median_price",
    "mid_price", "price",
)
LOW_FIELDS = ("low_price", "minimum_source_price", "market_value_low")
HIGH_FIELDS = ("high_price", "maximum_source_price", "market_value_high")
LISTING_FIELDS = ("listing_count", "accepted_listing_count", "results_found")
SELLER_FIELDS = ("seller_count", "accepted_seller_count")
SOURCE_FIELDS = ("source_name", "price_source", "source", "valuation_method")
RUN_FIELDS = ("source_run_id", "collection_run_id", "run_id")

EXCLUDED_PARTS = {".git", "__pycache__"}
EXCLUDED_FILENAMES = {
    "governed_marketplace_product_map.csv",
    "ebay_eligible_product_map.csv",
    "tcgcsv_eligible_product_map.csv",
    "marketplace_batch_product_map.csv",
    "ebay_product_map.csv",
    "tcgcsv_product_map.csv",
    "tcgcsv_product_map_source.csv",
}


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def first(row: dict[str, Any], fields: Iterable[str]) -> str:
    for field in fields:
        value = str(row.get(field, "") or "").strip()
        if value:
            return value
    return ""


def number(value: object) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        parsed = float(text)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def integer(value: object) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fingerprint(row: dict[str, Any]) -> str:
    payload = "|".join(str(row.get(key, "")) for key in (
        "canonical_product_id", "source_name", "source_file",
        "observation_date", "market_price", "low_price", "high_price",
        "listing_count", "seller_count",
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_indexes(universe: list[dict[str, str]]):
    by_canonical, by_tcgplayer, by_name = {}, {}, {}
    for row in universe:
        canonical_id = first(row, ("canonical_product_id",))
        if canonical_id:
            by_canonical[canonical_id] = row
        tcgplayer = first(row, TCGPLAYER_FIELDS)
        if tcgplayer:
            by_tcgplayer[tcgplayer] = row
        for field in NAME_FIELDS:
            value = norm(row.get(field))
            if value and value not in by_name:
                by_name[value] = row
    return by_canonical, by_tcgplayer, by_name


def resolve_product(row, by_canonical, by_tcgplayer, by_name):
    canonical = first(row, ID_FIELDS)
    if canonical and canonical in by_canonical:
        return by_canonical[canonical], "CANONICAL_ID"
    tcgplayer = first(row, TCGPLAYER_FIELDS)
    if tcgplayer and tcgplayer in by_tcgplayer:
        return by_tcgplayer[tcgplayer], "TCGPLAYER_ID"
    for field in NAME_FIELDS:
        candidate = norm(row.get(field))
        if candidate and candidate in by_name:
            return by_name[candidate], "NORMALIZED_NAME"
    return None, ""


def source_name(row: dict[str, str], path: Path) -> str:
    explicit = first(row, SOURCE_FIELDS)
    if explicit:
        return explicit.upper()
    lower = str(path).lower()
    if "ebay" in lower:
        return "EBAY"
    if "tcgcsv" in lower or "tcgplayer" in lower:
        return "TCGCSV"
    if "secret_lair" in lower:
        return "SECRET_LAIR_EVIDENCE"
    return "REPOSITORY_HISTORY"


def eligible_file(path: Path) -> bool:
    if path.name in EXCLUDED_FILENAMES:
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if "mtg_history_foundation" in str(path).lower():
        return False
    return path.suffix.lower() == ".csv"


def discover_files(scan_roots: Iterable[Path]) -> list[Path]:
    found, seen = [], set()
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            resolved = path.resolve()
            if resolved not in seen and eligible_file(resolved):
                seen.add(resolved)
                found.append(resolved)
    return sorted(found)


def extract_history(universe, files):
    by_canonical, by_tcgplayer, by_name = build_indexes(universe)
    normalized_rows = []
    scanned_files = candidate_rows = matched_rows = files_with_prices = 0
    mapping_methods = Counter()
    file_summaries = []

    for path in files:
        try:
            fields, rows = read_csv(path)
        except (UnicodeDecodeError, csv.Error, OSError):
            continue
        scanned_files += 1
        if not any(field in fields for field in PRICE_FIELDS):
            continue
        file_matched_rows = 0
        for row in rows:
            price, price_field = None, ""
            for field in PRICE_FIELDS:
                price = number(row.get(field))
                if price is not None:
                    price_field = field
                    break
            if price is None:
                continue
            candidate_rows += 1
            product, method = resolve_product(
                row, by_canonical, by_tcgplayer, by_name
            )
            if product is None:
                continue
            matched_rows += 1
            file_matched_rows += 1
            mapping_methods[method] += 1
            observation_date = first(row, DATE_FIELDS)
            normalized = {
                "canonical_product_id": first(product, ("canonical_product_id",)),
                "canonical_product_name": first(product, ("box_name", "source_product_name")),
                "product_class": first(product, ("product_class",)),
                "tcgplayer_product_id": first(product, TCGPLAYER_FIELDS),
                "source_name": source_name(row, path),
                "source_product_id": first(row, TCGPLAYER_FIELDS) or first(row, ID_FIELDS),
                "observation_date": observation_date,
                "observed_at_utc": observation_date,
                "market_price": round(price, 4),
                "low_price": number(first(row, LOW_FIELDS)) or "",
                "high_price": number(first(row, HIGH_FIELDS)) or "",
                "listing_count": integer(first(row, LISTING_FIELDS)) or "",
                "seller_count": integer(first(row, SELLER_FIELDS)) or "",
                "currency": str(row.get("currency") or "USD"),
                "price_field": price_field,
                "mapping_method": method,
                "source_file": str(path.relative_to(ROOT)),
                "collection_run_id": first(row, RUN_FIELDS),
                "is_live_observation": (
                    "true"
                    if "operations/mtg_marketplace" in str(path).replace("\\", "/")
                    else "false"
                ),
            }
            normalized["observation_fingerprint"] = fingerprint(normalized)
            normalized_rows.append(normalized)
        if file_matched_rows:
            files_with_prices += 1
            file_summaries.append({
                "source_file": str(path.relative_to(ROOT)),
                "rows": len(rows),
                "matched_price_rows": file_matched_rows,
            })

    deduplicated = {
        str(row["observation_fingerprint"]): row for row in normalized_rows
    }
    final_rows = list(deduplicated.values())
    final_rows.sort(key=lambda row: (
        str(row["canonical_product_id"]),
        str(row["observation_date"]),
        str(row["source_name"]),
        str(row["source_file"]),
    ))
    return final_rows, {
        "scanned_csv_files": scanned_files,
        "files_with_price_rows": files_with_prices,
        "candidate_price_rows": candidate_rows,
        "matched_price_rows_before_deduplication": matched_rows,
        "normalized_history_rows": len(final_rows),
        "mapping_method_counts": dict(sorted(mapping_methods.items())),
        "contributing_files": file_summaries,
    }


def build_coverage(universe, history):
    grouped = defaultdict(list)
    for row in history:
        grouped[str(row["canonical_product_id"])].append(row)

    coverage = []
    for product in universe:
        canonical_id = first(product, ("canonical_product_id",))
        rows = grouped.get(canonical_id, [])
        dates = sorted({
            str(row.get("observation_date") or "")
            for row in rows if str(row.get("observation_date") or "")
        })
        sources = sorted({
            str(row.get("source_name") or "")
            for row in rows if str(row.get("source_name") or "")
        })
        direct_rows = [
            row for row in rows
            if str(row.get("price_field")) not in {
                "evaluated_market_value_usd", "market_value_usd"
            }
        ]
        live_rows = [
            row for row in rows
            if str(row.get("is_live_observation")).lower() == "true"
        ]
        direct_count = len(direct_rows)
        if direct_count >= 30:
            status = "DIRECT_HISTORY_30_PLUS"
        elif direct_count >= 2:
            status = "DIRECT_HISTORY_LIMITED"
        elif direct_count == 1:
            status = "DIRECT_HISTORY_SINGLE"
        elif rows:
            status = "MODEL_OR_VALUATION_ONLY"
        else:
            status = "NO_HISTORY_FOUND"
        coverage.append({
            "canonical_product_id": canonical_id,
            "canonical_product_name": first(product, ("box_name", "source_product_name")),
            "product_class": first(product, ("product_class",)),
            "tcgplayer_product_id": first(product, TCGPLAYER_FIELDS),
            "collection_lane": first(product, ("collection_lane",)),
            "history_observation_count": len(rows),
            "direct_history_observation_count": direct_count,
            "live_observation_count": len(live_rows),
            "history_source_count": len(sources),
            "history_sources": "|".join(sources),
            "first_observation_date": dates[0] if dates else "",
            "latest_observation_date": dates[-1] if dates else "",
            "history_coverage_status": status,
            "has_tcgplayer_identity": "true" if first(product, TCGPLAYER_FIELDS) else "false",
            "has_ebay_identity": "true" if first(product, ("ebay_query",)) else "false",
            "full_model_ready_from_direct_history": "true" if direct_count >= 30 else "false",
        })
    coverage.sort(key=lambda row: str(row["canonical_product_id"]))
    return coverage


def build_identity(universe):
    rows = []
    for product in universe:
        canonical_id = first(product, ("canonical_product_id",))
        name = first(product, ("box_name", "source_product_name"))
        product_class = first(product, ("product_class",))
        rows.append({
            "canonical_product_id": canonical_id,
            "canonical_product_name": name,
            "product_class": product_class,
            "source_name": "CANONICAL",
            "source_product_id": canonical_id,
            "source_query": "",
            "identity_status": "GOVERNED",
        })
        tcgplayer = first(product, TCGPLAYER_FIELDS)
        if tcgplayer:
            rows.append({
                "canonical_product_id": canonical_id,
                "canonical_product_name": name,
                "product_class": product_class,
                "source_name": "TCGPLAYER",
                "source_product_id": tcgplayer,
                "source_query": "",
                "identity_status": "GOVERNED",
            })
        ebay_query = first(product, ("ebay_query",))
        rows.append({
            "canonical_product_id": canonical_id,
            "canonical_product_name": name,
            "product_class": product_class,
            "source_name": "EBAY",
            "source_product_id": "",
            "source_query": ebay_query,
            "identity_status": "GOVERNED" if ebay_query else "MISSING_QUERY",
        })
    return rows


def build_model_contract(coverage):
    rows = []
    for item in coverage:
        direct = int(item["direct_history_observation_count"])
        if direct >= 365:
            maturity = "MATURE_365_PLUS"
        elif direct >= 180:
            maturity = "DEVELOPING_180_PLUS"
        elif direct >= 30:
            maturity = "MINIMUM_FULL_MODEL_HISTORY"
        elif direct > 0:
            maturity = "SHORT_DIRECT_HISTORY"
        else:
            maturity = "NO_DIRECT_HISTORY"
        rows.append({
            "canonical_product_id": item["canonical_product_id"],
            "canonical_product_name": item["canonical_product_name"],
            "product_class": item["product_class"],
            "tcgplayer_product_id": item["tcgplayer_product_id"],
            "required_model_status": "FULL_MODEL_REQUIRED",
            "current_model_readiness": maturity,
            "direct_history_observation_count": direct,
            "history_source_count": item["history_source_count"],
            "live_collection_required": "true",
            "historical_backfill_required": "false" if direct >= 365 else "true",
            "model_output_required": "true",
            "forecast_1y_required": "true",
            "forecast_3y_required": "true",
            "forecast_5y_required": "true",
            "prob_loss_required": "true",
            "prob_double_required": "true",
            "recommendation_required": "true",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the universal 1,141-product MTG history foundation."
    )
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    _, universe = read_csv(args.universe.resolve())
    if len(universe) != 1141:
        raise SystemExit(
            f"Governed universe must contain 1,141 rows; found {len(universe)}"
        )
    canonical_ids = [first(row, ("canonical_product_id",)) for row in universe]
    if len(set(canonical_ids)) != 1141 or any(not value for value in canonical_ids):
        raise SystemExit("Governed universe canonical IDs are missing or duplicated")

    history, audit = extract_history(universe, discover_files(SCAN_ROOTS))
    coverage = build_coverage(universe, history)
    identity = build_identity(universe)
    contract = build_model_contract(coverage)

    output = args.output_root.resolve()
    write_csv(output / "universal_mtg_price_history.csv", history, [
        "canonical_product_id", "canonical_product_name", "product_class",
        "tcgplayer_product_id", "source_name", "source_product_id",
        "observation_date", "observed_at_utc", "market_price",
        "low_price", "high_price", "listing_count", "seller_count",
        "currency", "price_field", "mapping_method", "source_file",
        "collection_run_id", "is_live_observation", "observation_fingerprint",
    ])
    write_csv(
        output / "universal_mtg_history_coverage.csv",
        coverage,
        list(coverage[0].keys()),
    )
    write_csv(
        output / "universal_mtg_source_identity.csv",
        identity,
        list(identity[0].keys()),
    )
    write_csv(
        output / "universal_mtg_full_model_contract.csv",
        contract,
        list(contract[0].keys()),
    )

    coverage_counts = Counter(str(row["history_coverage_status"]) for row in coverage)
    readiness_counts = Counter(str(row["current_model_readiness"]) for row in contract)
    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governed_products": len(universe),
        "history_coverage_rows": len(coverage),
        "source_identity_rows": len(identity),
        "full_model_contract_rows": len(contract),
        "normalized_history_rows": len(history),
        "products_with_any_history": sum(
            int(row["history_observation_count"]) > 0 for row in coverage
        ),
        "products_with_direct_history": sum(
            int(row["direct_history_observation_count"]) > 0 for row in coverage
        ),
        "products_with_live_history": sum(
            int(row["live_observation_count"]) > 0 for row in coverage
        ),
        "products_ready_for_minimum_full_model_history": sum(
            str(row["full_model_ready_from_direct_history"]) == "true"
            for row in coverage
        ),
        "products_requiring_historical_backfill": sum(
            str(row["historical_backfill_required"]) == "true"
            for row in contract
        ),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "model_readiness_counts": dict(sorted(readiness_counts.items())),
        "audit": audit,
        "certification_checks": {
            "governed_products_equal_1141": len(universe) == 1141,
            "history_coverage_rows_equal_1141": len(coverage) == 1141,
            "full_model_contract_rows_equal_1141": len(contract) == 1141,
            "canonical_ids_unique": len(set(canonical_ids)) == 1141,
            "all_products_require_full_model": all(
                row["required_model_status"] == "FULL_MODEL_REQUIRED"
                for row in contract
            ),
            "all_products_require_live_collection": all(
                row["live_collection_required"] == "true"
                for row in contract
            ),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    (output / "universal_mtg_history_foundation_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
