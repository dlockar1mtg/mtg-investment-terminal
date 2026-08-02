from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_ebay_supply_reconstruction_contract_v1.json"
SEARCH_ROOT = ROOT / "data/governance/permanence/certification"
OUTPUT_DIR = SEARCH_ROOT / "collector_v1_august1_ebay_supply_reconstruction"
CANONICAL = SEARCH_ROOT / "collector_v1_august1_current_data_package/collector_ebay_product_supply_snapshot.csv"


def clean(value: Any) -> str:
    return str(value or "").strip()


def numeric_id(value: Any) -> str:
    text = clean(value)
    return "".join(character for character in text if character.isdigit())


def num(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first(row: dict[str, Any], names: list[str]) -> str:
    for name in names:
        if clean(row.get(name)):
            return clean(row.get(name))
    return ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def detect_universe(contract: dict[str, Any]) -> tuple[Path, list[dict[str, str]]]:
    candidates: list[tuple[int, str, Path, list[dict[str, str]]]] = []
    for path in SEARCH_ROOT.rglob("*.csv"):
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if len(rows) != contract["required_product_rows"] or not rows:
            continue
        headers = set(rows[0])
        if "tcgplayer_product_id" not in headers:
            continue
        identity = "canonical_product_id" in headers
        names = "product_name" in headers
        if not (identity and names):
            continue
        score = 0
        path_text = str(path).lower()
        if "final_current_price_authority" in path_text:
            score += 20
        if "premodel" in path_text:
            score += 5
        if "current_price" in path_text:
            score += 3
        candidates.append((score, str(path), path, rows))
    if not candidates:
        raise RuntimeError("NO_50_PRODUCT_UNIVERSE_FOUND")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2], candidates[0][3]


def detect_listing_ledger(contract: dict[str, Any]) -> tuple[Path, list[dict[str, str]]]:
    candidates: list[tuple[int, str, Path, list[dict[str, str]]]] = []
    for path in SEARCH_ROOT.rglob("*.csv"):
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if len(rows) != contract["required_accepted_listing_rows"] or not rows:
            continue
        headers = set(rows[0])
        identity = any(
            header in headers
            for header in [
                "resolved_tcgplayer_product_id",
                "tcgplayer_product_id",
                "canonical_product_id",
            ]
        )
        price = any(
            header in headers
            for header in ["landed_price", "total_price", "listing_price", "price", "item_price"]
        )
        if not (identity and price):
            continue
        score = 0
        path_text = str(path).lower()
        if "accepted_listing_ledger" in path_text:
            score += 20
        if "accepted" in path_text:
            score += 5
        if "ledger" in path_text:
            score += 3
        if "ebay" in path_text:
            score += 2
        candidates.append((score, str(path), path, rows))
    if not candidates:
        raise RuntimeError("NO_562_ROW_ACCEPTED_LISTING_LEDGER_FOUND")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2], candidates[0][3]


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    universe_path: Path | None = None
    listing_path: Path | None = None
    universe_rows: list[dict[str, str]] = []
    listing_rows: list[dict[str, str]] = []

    try:
        universe_path, universe_rows = detect_universe(contract)
    except RuntimeError as error:
        failures.append(str(error))

    try:
        listing_path, listing_rows = detect_listing_ledger(contract)
    except RuntimeError as error:
        failures.append(str(error))

    universe_by_tcgplayer_id: dict[str, dict[str, str]] = {}
    canonical_ids: set[str] = set()
    for row in universe_rows:
        tcgplayer_id = numeric_id(row.get("tcgplayer_product_id"))
        canonical_id = clean(row.get("canonical_product_id"))
        product_name = clean(row.get("product_name"))
        if not tcgplayer_id or not canonical_id or not product_name:
            continue
        if tcgplayer_id in universe_by_tcgplayer_id:
            failures.append("DUPLICATE_UNIVERSE_TCGPLAYER_PRODUCT_ID")
        if canonical_id in canonical_ids:
            failures.append("DUPLICATE_UNIVERSE_CANONICAL_PRODUCT_ID")
        universe_by_tcgplayer_id[tcgplayer_id] = {
            "canonical_product_id": canonical_id,
            "tcgplayer_product_id": tcgplayer_id,
            "product_name": product_name,
        }
        canonical_ids.add(canonical_id)

    if len(universe_by_tcgplayer_id) != contract["required_product_rows"]:
        failures.append("UNIVERSE_IDENTITY_COUNT_MISMATCH")

    by_tcgplayer_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    unknown_listing_ids: set[str] = set()
    blank_listing_ids = 0

    for row in listing_rows:
        listing_tcgplayer_id = numeric_id(
            first(
                row,
                [
                    "resolved_tcgplayer_product_id",
                    "tcgplayer_product_id",
                    "canonical_product_id",
                ],
            )
        )
        if not listing_tcgplayer_id:
            blank_listing_ids += 1
            continue
        if listing_tcgplayer_id not in universe_by_tcgplayer_id:
            unknown_listing_ids.add(listing_tcgplayer_id)
            continue
        by_tcgplayer_id[listing_tcgplayer_id].append(row)

    if blank_listing_ids:
        failures.append("BLANK_LISTING_PRODUCT_IDS")
    if unknown_listing_ids:
        failures.append("UNKNOWN_LISTING_PRODUCT_IDS")
    if len(listing_rows) != contract["required_accepted_listing_rows"]:
        failures.append("ACCEPTED_LISTING_COUNT_MISMATCH")

    mapped_listing_rows = sum(len(rows) for rows in by_tcgplayer_id.values())
    if mapped_listing_rows != contract["required_accepted_listing_rows"]:
        failures.append("MAPPED_LISTING_COUNT_MISMATCH")

    positive_counts = [len(rows) for rows in by_tcgplayer_id.values() if rows]
    q25, q50, q75 = (
        percentile(positive_counts, quantile)
        for quantile in (0.25, 0.50, 0.75)
    )

    output_rows: list[dict[str, Any]] = []
    for tcgplayer_id, authority in sorted(
        universe_by_tcgplayer_id.items(),
        key=lambda item: item[1]["product_name"].lower(),
    ):
        items = by_tcgplayer_id.get(tcgplayer_id, [])
        listing_count = len(items)

        if listing_count == 0:
            supply_category = "ZERO_OBSERVED_SUPPLY"
        elif listing_count <= q25:
            supply_category = "ULTRA_THIN_SUPPLY"
        elif listing_count <= q50:
            supply_category = "THIN_SUPPLY"
        elif listing_count <= q75:
            supply_category = "MODERATE_SUPPLY"
        else:
            supply_category = "DEEP_SUPPLY"

        sellers = [
            first(
                row,
                ["seller_hash", "seller_username", "seller_id", "seller", "seller_name"],
            )
            for row in items
        ]
        sellers = [seller for seller in sellers if seller]
        seller_counts = Counter(sellers)
        distinct_seller_count: int | str = len(seller_counts) if sellers else ""
        seller_concentration: float | str = (
            max(seller_counts.values()) / listing_count
            if seller_counts and listing_count
            else ""
        )

        prices: list[float] = []
        for row in items:
            price = num(
                first(
                    row,
                    ["landed_price", "total_price", "listing_price", "price", "item_price"],
                )
            )
            if price is not None and price > 0:
                prices.append(price)
        prices.sort()

        price_q25: float | str = percentile(prices, 0.25) if prices else ""
        price_q75: float | str = percentile(prices, 0.75) if prices else ""
        median_price: float | str = median(prices) if prices else ""
        price_dispersion: float | str = (
            (price_q75 - price_q25) / median_price
            if prices and median_price
            else ""
        )

        output_rows.append(
            {
                "canonical_product_id": authority["canonical_product_id"],
                "tcgplayer_product_id": tcgplayer_id,
                "product_name": authority["product_name"],
                "accepted_listing_count": listing_count,
                "supply_category": supply_category,
                "distinct_seller_count": distinct_seller_count,
                "seller_concentration": seller_concentration,
                "median_listing_price": median_price,
                "minimum_listing_price": min(prices) if prices else "",
                "maximum_listing_price": max(prices) if prices else "",
                "listing_price_p25": price_q25,
                "listing_price_p75": price_q75,
                "listing_price_dispersion": price_dispersion,
                "zero_accepted_listings": listing_count == 0,
                "supply_observation_date": "2026-08-01",
                "source_snapshot_id": contract["snapshot_id"],
                "source_listing_ledger_path": ""
                if listing_path is None
                else str(listing_path.relative_to(ROOT)),
                "source_listing_ledger_sha256": ""
                if listing_path is None
                else sha256(listing_path),
                "identity_bridge": "AUTHORITY_TCGPLAYER_PRODUCT_ID_TO_LEDGER_RESOLVED_TCGPLAYER_PRODUCT_ID",
                "purchase_recommendation_authorized": False,
            }
        )

    aggregated_listing_count = sum(
        int(row["accepted_listing_count"])
        for row in output_rows
    )
    if aggregated_listing_count != contract["required_accepted_listing_rows"]:
        failures.append("AGGREGATED_LISTING_COUNT_DOES_NOT_RECONCILE")
    if len(output_rows) != contract["required_product_rows"]:
        failures.append("SUPPLY_OUTPUT_ROW_COUNT_MISMATCH")

    fields = [
        "canonical_product_id",
        "tcgplayer_product_id",
        "product_name",
        "accepted_listing_count",
        "supply_category",
        "distinct_seller_count",
        "seller_concentration",
        "median_listing_price",
        "minimum_listing_price",
        "maximum_listing_price",
        "listing_price_p25",
        "listing_price_p75",
        "listing_price_dispersion",
        "zero_accepted_listings",
        "supply_observation_date",
        "source_snapshot_id",
        "source_listing_ledger_path",
        "source_listing_ledger_sha256",
        "identity_bridge",
        "purchase_recommendation_authorized",
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        OUTPUT_DIR / "collector_august1_ebay_supply_snapshot.csv",
        output_rows,
        fields,
    )
    write_csv(
        OUTPUT_DIR / "collector_august1_ebay_supply_category_summary.csv",
        [
            {
                "supply_category": category,
                "product_count": sum(
                    1
                    for row in output_rows
                    if row["supply_category"] == category
                ),
            }
            for category in contract["supply_categories"]
        ],
        ["supply_category", "product_count"],
    )
    write_csv(
        OUTPUT_DIR / "collector_august1_ebay_supply_source_selection.csv",
        [
            {
                "product_universe_path": ""
                if universe_path is None
                else str(universe_path.relative_to(ROOT)),
                "listing_ledger_path": ""
                if listing_path is None
                else str(listing_path.relative_to(ROOT)),
                "listing_ledger_sha256": ""
                if listing_path is None
                else sha256(listing_path),
                "identity_bridge": "AUTHORITY_TCGPLAYER_PRODUCT_ID_TO_LEDGER_RESOLVED_TCGPLAYER_PRODUCT_ID",
                "listing_rows": len(listing_rows),
                "mapped_listing_rows": mapped_listing_rows,
                "positive_supply_products": sum(
                    1 for row in output_rows if int(row["accepted_listing_count"]) > 0
                ),
                "zero_supply_products": sum(
                    1 for row in output_rows if int(row["accepted_listing_count"]) == 0
                ),
                "product_rows": len(output_rows),
                "q25_positive_listing_count": q25,
                "median_positive_listing_count": q50,
                "q75_positive_listing_count": q75,
            }
        ],
        [
            "product_universe_path",
            "listing_ledger_path",
            "listing_ledger_sha256",
            "identity_bridge",
            "listing_rows",
            "mapped_listing_rows",
            "positive_supply_products",
            "zero_supply_products",
            "product_rows",
            "q25_positive_listing_count",
            "median_positive_listing_count",
            "q75_positive_listing_count",
        ],
    )

    canonical_created = False
    if not failures:
        CANONICAL.parent.mkdir(parents=True, exist_ok=True)
        write_csv(CANONICAL, output_rows, fields)
        canonical_created = True

    summary = {
        "block_name": "Collector August 1 Listing-Ledger Supply Reconstruction",
        "block_version": "1.0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "product_universe_path": ""
        if universe_path is None
        else str(universe_path.relative_to(ROOT)),
        "listing_ledger_path": ""
        if listing_path is None
        else str(listing_path.relative_to(ROOT)),
        "identity_bridge": "AUTHORITY_TCGPLAYER_PRODUCT_ID_TO_LEDGER_RESOLVED_TCGPLAYER_PRODUCT_ID",
        "accepted_listing_rows": len(listing_rows),
        "mapped_listing_rows": mapped_listing_rows,
        "product_rows": len(output_rows),
        "products_with_positive_supply": sum(
            1 for row in output_rows if int(row["accepted_listing_count"]) > 0
        ),
        "products_with_zero_supply": sum(
            1 for row in output_rows if int(row["accepted_listing_count"]) == 0
        ),
        "positive_supply_q25": q25,
        "positive_supply_median": q50,
        "positive_supply_q75": q75,
        "canonical_output_path": str(CANONICAL.relative_to(ROOT))
        if canonical_created
        else "",
        "canonical_copy_created": canonical_created,
        "historical_backtest_use_allowed": False,
        "point_forecast_rewrite_allowed": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_AUGUST1_LISTING_LEDGER_SUPPLY_RECONSTRUCTION"
        if not failures
        else "FAIL_COLLECTOR_AUGUST1_LISTING_LEDGER_SUPPLY_RECONSTRUCTION",
    }

    (OUTPUT_DIR / "collector_august1_ebay_supply_reconstruction_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
