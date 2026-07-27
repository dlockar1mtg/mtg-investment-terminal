from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY = ROOT / "data" / "operations" / "mtg_history_foundation" / "universal_mtg_price_history.csv"
DEFAULT_COVERAGE = ROOT / "data" / "operations" / "mtg_history_foundation" / "universal_mtg_history_coverage.csv"
DEFAULT_OUTPUT = ROOT / "data" / "operations" / "mtg_history_backfill"

MODEL_FIELDS = {"evaluated_market_value_usd", "market_value_usd"}

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def number(value: object) -> float | None:
    try:
        text = str(value or "").replace("$", "").replace(",", "").strip()
        parsed = float(text)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None

def integer(value: object) -> int:
    parsed = number(value)
    return int(parsed) if parsed is not None else 0

def normalize_date(value: object) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text

def build_daily_source(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if str(row.get("price_field") or "") in MODEL_FIELDS:
            continue
        product_id = str(row.get("canonical_product_id") or "").strip()
        source = str(row.get("source_name") or "").strip()
        date = normalize_date(row.get("observation_date"))
        price = number(row.get("market_price"))
        if not product_id or not source or not date or price is None:
            continue
        grouped[(product_id, source, date)].append(row)

    output = []
    for (product_id, source, date), group in grouped.items():
        prices = [number(row.get("market_price")) for row in group]
        prices = [value for value in prices if value is not None]
        first = group[0]
        output.append({
            "canonical_product_id": product_id,
            "canonical_product_name": first.get("canonical_product_name", ""),
            "product_class": first.get("product_class", ""),
            "tcgplayer_product_id": first.get("tcgplayer_product_id", ""),
            "source_name": source,
            "observation_date": date,
            "daily_market_price": round(float(statistics.median(prices)), 4),
            "raw_observation_count": len(group),
            "listing_count": max(integer(row.get("listing_count")) for row in group),
            "seller_count": max(integer(row.get("seller_count")) for row in group),
            "source_file_count": len({row.get("source_file", "") for row in group}),
            "is_live_observation": "true" if any(str(row.get("is_live_observation")).lower() == "true" for row in group) else "false",
        })
    output.sort(key=lambda row: (str(row["canonical_product_id"]), str(row["observation_date"]), str(row["source_name"])))
    return output

def build_daily_consolidated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["canonical_product_id"]), str(row["observation_date"]))].append(row)
    output = []
    for (product_id, date), group in grouped.items():
        prices = [float(row["daily_market_price"]) for row in group]
        first = group[0]
        sources = sorted({str(row["source_name"]) for row in group})
        output.append({
            "canonical_product_id": product_id,
            "canonical_product_name": first.get("canonical_product_name", ""),
            "product_class": first.get("product_class", ""),
            "tcgplayer_product_id": first.get("tcgplayer_product_id", ""),
            "observation_date": date,
            "consolidated_market_price": round(float(statistics.median(prices)), 4),
            "minimum_source_price": round(min(prices), 4),
            "maximum_source_price": round(max(prices), 4),
            "source_count": len(sources),
            "source_names": "|".join(sources),
            "raw_observation_count": sum(int(row["raw_observation_count"]) for row in group),
            "is_live_observation": "true" if any(str(row.get("is_live_observation")).lower() == "true" for row in group) else "false",
        })
    output.sort(key=lambda row: (str(row["canonical_product_id"]), str(row["observation_date"])))
    return output

def build_verification(coverage_rows: list[dict[str, str]], daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        by_product[str(row["canonical_product_id"])].append(row)
    output = []
    for coverage in coverage_rows:
        product_id = str(coverage.get("canonical_product_id") or "")
        rows = by_product.get(product_id, [])
        dates = sorted({str(row["observation_date"]) for row in rows})
        sources = sorted({str(row.get("source_names") or row.get("source_name") or "") for row in rows})
        tcg_id = str(coverage.get("tcgplayer_product_id") or "").strip()
        if len(dates) >= 365:
            status = "HISTORY_365_PLUS_DATES"
        elif len(dates) >= 180:
            status = "HISTORY_180_TO_364_DATES"
        elif len(dates) >= 30:
            status = "HISTORY_30_TO_179_DATES"
        elif len(dates) >= 2:
            status = "HISTORY_2_TO_29_DATES"
        elif len(dates) == 1:
            status = "HISTORY_SINGLE_DATE"
        else:
            status = "NO_DIRECT_DATED_HISTORY_FOUND"
        output.append({
            "canonical_product_id": product_id,
            "canonical_product_name": coverage.get("canonical_product_name", ""),
            "product_class": coverage.get("product_class", ""),
            "tcgplayer_product_id": tcg_id,
            "tcgcsv_identity_status": "TCGCSV_ID_CONFIRMED" if tcg_id else "TCGCSV_ID_NOT_CONFIRMED",
            "ebay_identity_status": "EBAY_QUERY_CONFIRMED" if str(coverage.get("has_ebay_identity")).lower() == "true" else "EBAY_QUERY_MISSING",
            "distinct_history_dates": len(dates),
            "first_history_date": dates[0] if dates else "",
            "latest_history_date": dates[-1] if dates else "",
            "history_source_count": len([s for s in sources if s]),
            "history_sources": "|".join([s for s in sources if s]),
            "history_verification_status": status,
            "fresh_tcgcsv_archive_search_status": "NOT_YET_EXECUTED",
            "source_exhaustion_status": "NOT_CERTIFIED",
            "live_history_accumulation_required": "false" if len(dates) >= 365 else "true",
        })
    output.sort(key=lambda row: str(row["canonical_product_id"]))
    return output

def main() -> int:
    parser = argparse.ArgumentParser(description="Build distinct-date MTG history and source-verification outputs.")
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    history = read_csv(args.history.resolve())
    coverage = read_csv(args.coverage.resolve())
    if len(coverage) != 1141:
        raise SystemExit(f"Expected 1,141 coverage rows; found {len(coverage)}")

    daily_source = build_daily_source(history)
    daily_consolidated = build_daily_consolidated(daily_source)
    verification = build_verification(coverage, daily_consolidated)

    output = args.output_root.resolve()
    write_csv(output / "universal_mtg_daily_source_history.csv", daily_source, list(daily_source[0].keys()) if daily_source else [
        "canonical_product_id","canonical_product_name","product_class","tcgplayer_product_id","source_name","observation_date","daily_market_price","raw_observation_count","listing_count","seller_count","source_file_count","is_live_observation"
    ])
    write_csv(output / "universal_mtg_daily_consolidated_history.csv", daily_consolidated, list(daily_consolidated[0].keys()) if daily_consolidated else [
        "canonical_product_id","canonical_product_name","product_class","tcgplayer_product_id","observation_date","consolidated_market_price","minimum_source_price","maximum_source_price","source_count","source_names","raw_observation_count","is_live_observation"
    ])
    write_csv(output / "universal_mtg_history_source_verification.csv", verification, list(verification[0].keys()))

    counts = Counter(str(row["history_verification_status"]) for row in verification)
    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "governed_products": len(verification),
        "daily_source_rows": len(daily_source),
        "daily_consolidated_rows": len(daily_consolidated),
        "products_with_dated_history": sum(int(row["distinct_history_dates"]) > 0 for row in verification),
        "products_with_30_plus_distinct_dates": sum(int(row["distinct_history_dates"]) >= 30 for row in verification),
        "products_with_no_direct_dated_history": sum(int(row["distinct_history_dates"]) == 0 for row in verification),
        "tcgcsv_identity_confirmed_products": sum(row["tcgcsv_identity_status"] == "TCGCSV_ID_CONFIRMED" for row in verification),
        "tcgcsv_identity_unconfirmed_products": sum(row["tcgcsv_identity_status"] == "TCGCSV_ID_NOT_CONFIRMED" for row in verification),
        "fresh_tcgcsv_archive_search_executed": False,
        "source_exhaustion_certified": False,
        "history_verification_status_counts": dict(sorted(counts.items())),
        "certification_checks": {
            "verification_rows_equal_1141": len(verification) == 1141,
            "canonical_ids_unique": len({row["canonical_product_id"] for row in verification}) == 1141,
            "all_products_have_history_status": all(row["history_verification_status"] for row in verification),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"
    (output / "universal_mtg_history_backfill_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
