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


def clean(v: Any) -> str:
    return str(v or "").strip()


def num(v: Any) -> float | None:
    t = clean(v).replace("$", "").replace(",", "")
    if not t:
        return None
    try:
        x = float(t)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def first(row: dict[str, Any], names: list[str]) -> str:
    for n in names:
        if clean(row.get(n)):
            return clean(row.get(n))
    return ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    p = (len(values) - 1) * q
    lo, hi = math.floor(p), math.ceil(p)
    if lo == hi:
        return values[lo]
    w = p - lo
    return values[lo] * (1 - w) + values[hi] * w


def detect_universe(contract: dict[str, Any]) -> tuple[Path, list[dict[str, str]]]:
    candidates: list[tuple[int, str, Path, list[dict[str, str]]]] = []
    for path in SEARCH_ROOT.rglob("*.csv"):
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if len(rows) != contract["required_product_rows"]:
            continue
        headers = set(rows[0]) if rows else set()
        identity = any(h in headers for h in ["canonical_product_id", "target_canonical_product_id", "product_id"])
        names = any(h in headers for h in ["product_name", "target_product_name", "name"])
        if identity and names:
            score = 0
            text = str(path).lower()
            if "full_universe" in text: score += 5
            if "coverage" in text: score += 2
            if "ebay" in text: score += 2
            candidates.append((score, str(path), path, rows))
    if not candidates:
        raise RuntimeError("NO_50_PRODUCT_UNIVERSE_FOUND")
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2], candidates[0][3]


def detect_listing_ledger(contract: dict[str, Any]) -> tuple[Path, list[dict[str, str]]]:
    candidates: list[tuple[int, str, Path, list[dict[str, str]]]] = []
    for path in SEARCH_ROOT.rglob("*.csv"):
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if len(rows) != contract["required_accepted_listing_rows"]:
            continue
        if not rows:
            continue
        headers = set(rows[0])
        identity = any(h in headers for h in ["canonical_product_id", "target_canonical_product_id", "product_id"])
        price = any(h in headers for h in ["total_price", "listing_price", "price", "item_price", "current_price"])
        if not (identity and price):
            continue
        text = str(path).lower(); score = 0
        if "accepted" in text: score += 5
        if "ledger" in text: score += 3
        if "ebay" in text: score += 2
        candidates.append((score, str(path), path, rows))
    if not candidates:
        raise RuntimeError("NO_562_ROW_ACCEPTED_LISTING_LEDGER_FOUND")
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2], candidates[0][3]


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    failures: list[str] = []
    universe_path = listing_path = None
    universe_rows: list[dict[str, str]] = []
    listing_rows: list[dict[str, str]] = []
    try:
        universe_path, universe_rows = detect_universe(contract)
    except RuntimeError as e:
        failures.append(str(e))
    try:
        listing_path, listing_rows = detect_listing_ledger(contract)
    except RuntimeError as e:
        failures.append(str(e))

    universe: dict[str, str] = {}
    for r in universe_rows:
        cid = first(r, ["canonical_product_id", "target_canonical_product_id", "product_id"])
        name = first(r, ["product_name", "target_product_name", "name"])
        if cid:
            universe[cid] = name
    if len(universe) != contract["required_product_rows"]:
        failures.append("UNIVERSE_IDENTITY_COUNT_MISMATCH")

    by_product: dict[str, list[dict[str, str]]] = defaultdict(list)
    unknown_ids: set[str] = set()
    for r in listing_rows:
        cid = first(r, ["canonical_product_id", "target_canonical_product_id", "product_id"])
        if cid not in universe:
            unknown_ids.add(cid)
        else:
            by_product[cid].append(r)
    if unknown_ids:
        failures.append("UNKNOWN_LISTING_PRODUCT_IDS")
    if len(listing_rows) != contract["required_accepted_listing_rows"]:
        failures.append("ACCEPTED_LISTING_COUNT_MISMATCH")

    positive_counts = [len(v) for v in by_product.values() if len(v) > 0]
    q25, q50, q75 = (percentile(positive_counts, q) for q in (0.25, 0.50, 0.75))

    rows: list[dict[str, Any]] = []
    for cid, name in sorted(universe.items(), key=lambda x: x[1].lower()):
        items = by_product.get(cid, [])
        count = len(items)
        if count == 0:
            tier = "ZERO_OBSERVED_SUPPLY"
        elif count <= q25:
            tier = "ULTRA_THIN_SUPPLY"
        elif count <= q50:
            tier = "THIN_SUPPLY"
        elif count <= q75:
            tier = "MODERATE_SUPPLY"
        else:
            tier = "DEEP_SUPPLY"

        sellers = [first(r, ["seller_username", "seller_id", "seller", "seller_name"]) for r in items]
        sellers = [s for s in sellers if s]
        seller_counts = Counter(sellers)
        distinct = len(seller_counts) if sellers else ""
        top_share = (max(seller_counts.values()) / count) if seller_counts and count else ""

        prices = []
        for r in items:
            p = num(first(r, ["total_price", "listing_price", "price", "item_price", "current_price"]))
            if p is not None and p > 0:
                prices.append(p)
        prices.sort()
        p25 = percentile(prices, 0.25) if prices else ""
        p75 = percentile(prices, 0.75) if prices else ""
        med = median(prices) if prices else ""
        dispersion = ((p75 - p25) / med) if prices and med else ""

        rows.append({
            "canonical_product_id": cid,
            "product_name": name,
            "accepted_listing_count": count,
            "supply_category": tier,
            "distinct_seller_count": distinct,
            "seller_concentration": top_share,
            "median_listing_price": med,
            "minimum_listing_price": min(prices) if prices else "",
            "maximum_listing_price": max(prices) if prices else "",
            "listing_price_p25": p25,
            "listing_price_p75": p75,
            "listing_price_dispersion": dispersion,
            "zero_accepted_listings": count == 0,
            "supply_observation_date": "2026-08-01",
            "source_snapshot_id": contract["snapshot_id"],
            "source_listing_ledger_path": "" if listing_path is None else str(listing_path.relative_to(ROOT)),
            "source_listing_ledger_sha256": "" if listing_path is None else sha256(listing_path),
            "purchase_recommendation_authorized": False,
        })

    if sum(int(r["accepted_listing_count"]) for r in rows) != contract["required_accepted_listing_rows"]:
        failures.append("AGGREGATED_LISTING_COUNT_DOES_NOT_RECONCILE")
    if len(rows) != contract["required_product_rows"]:
        failures.append("SUPPLY_OUTPUT_ROW_COUNT_MISMATCH")

    fields = [
        "canonical_product_id", "product_name", "accepted_listing_count", "supply_category",
        "distinct_seller_count", "seller_concentration", "median_listing_price",
        "minimum_listing_price", "maximum_listing_price", "listing_price_p25", "listing_price_p75",
        "listing_price_dispersion", "zero_accepted_listings", "supply_observation_date",
        "source_snapshot_id", "source_listing_ledger_path", "source_listing_ledger_sha256",
        "purchase_recommendation_authorized"
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT_DIR / "collector_august1_ebay_supply_snapshot.csv", rows, fields)
    write_csv(OUTPUT_DIR / "collector_august1_ebay_supply_category_summary.csv", [
        {"supply_category": c, "product_count": sum(1 for r in rows if r["supply_category"] == c)}
        for c in contract["supply_categories"]
    ], ["supply_category", "product_count"])
    write_csv(OUTPUT_DIR / "collector_august1_ebay_supply_source_selection.csv", [{
        "product_universe_path": "" if universe_path is None else str(universe_path.relative_to(ROOT)),
        "listing_ledger_path": "" if listing_path is None else str(listing_path.relative_to(ROOT)),
        "listing_ledger_sha256": "" if listing_path is None else sha256(listing_path),
        "listing_rows": len(listing_rows),
        "product_rows": len(rows),
        "q25_positive_listing_count": q25,
        "median_positive_listing_count": q50,
        "q75_positive_listing_count": q75
    }], ["product_universe_path", "listing_ledger_path", "listing_ledger_sha256", "listing_rows", "product_rows", "q25_positive_listing_count", "median_positive_listing_count", "q75_positive_listing_count"])

    canonical_created = False
    if not failures:
        CANONICAL.parent.mkdir(parents=True, exist_ok=True)
        write_csv(CANONICAL, rows, fields)
        canonical_created = True

    summary = {
        "block_name": "Collector August 1 Listing-Ledger Supply Reconstruction",
        "block_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": contract["snapshot_id"],
        "product_universe_path": "" if universe_path is None else str(universe_path.relative_to(ROOT)),
        "listing_ledger_path": "" if listing_path is None else str(listing_path.relative_to(ROOT)),
        "accepted_listing_rows": len(listing_rows),
        "product_rows": len(rows),
        "products_with_positive_supply": sum(1 for r in rows if int(r["accepted_listing_count"]) > 0),
        "products_with_zero_supply": sum(1 for r in rows if int(r["accepted_listing_count"]) == 0),
        "positive_supply_q25": q25,
        "positive_supply_median": q50,
        "positive_supply_q75": q75,
        "canonical_output_path": str(CANONICAL.relative_to(ROOT)) if canonical_created else "",
        "canonical_copy_created": canonical_created,
        "historical_backtest_use_allowed": False,
        "point_forecast_rewrite_allowed": False,
        "purchase_recommendations_authorized": False,
        "critical_failures": failures,
        "status": "PASS_COLLECTOR_AUGUST1_LISTING_LEDGER_SUPPLY_RECONSTRUCTION" if not failures else "FAIL_COLLECTOR_AUGUST1_LISTING_LEDGER_SUPPLY_RECONSTRUCTION"
    }
    (OUTPUT_DIR / "collector_august1_ebay_supply_reconstruction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
