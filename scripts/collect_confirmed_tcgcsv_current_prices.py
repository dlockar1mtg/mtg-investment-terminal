from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_MAP = ROOT / "data/operations/mtg_tcgcsv_price_backfill/confirmed_tcgcsv_product_map.csv"
OUTPUT = ROOT / "data/operations/mtg_tcgcsv_price_backfill/current"

FIELDS = [
    "observation_id",
    "run_id",
    "observation_date",
    "collected_at_utc",
    "investment_product_id",
    "tcgplayer_product_id",
    "tcgcsv_category_id",
    "tcgcsv_group_id",
    "source_product_name",
    "sub_type_name",
    "market_price",
    "low_price",
    "mid_price",
    "high_price",
    "direct_low_price",
    "selected_price",
    "selection_method",
    "price_data_quality",
    "source_name",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def session() -> requests.Session:
    retry = Retry(
        total=5, connect=5, read=5, status=5, backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"], raise_on_status=False,
    )
    result = requests.Session()
    result.headers.update({
        "User-Agent": "MTGInvestmentTerminal/11E.7 (confirmed-price-backfill; personal use)",
        "Accept": "application/json",
    })
    adapter = HTTPAdapter(max_retries=retry)
    result.mount("https://", adapter)
    return result


def as_float(value: Any) -> float | None:
    try:
        if value in (None, "", "null"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    if isinstance(payload, list):
        return payload
    return []


def select_price(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not matches:
        return None
    for row in matches:
        subtype = str(row.get("subTypeName") or row.get("sub_type_name") or "").casefold()
        if subtype in ("normal", ""):
            return row
    return matches[0]


def collect(product_map: list[dict[str, str]], sleep_seconds: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    run_id = now.strftime("tcgcsv-live-%Y%m%dT%H%M%SZ")
    collected_at = now.isoformat()
    observation_date = now.date().isoformat()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in product_map:
        grouped.setdefault((row["tcgcsv_category_id"], row["tcgcsv_group_id"]), []).append(row)

    output: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    client = session()

    for index, ((category_id, group_id), products) in enumerate(sorted(grouped.items()), start=1):
        url = f"https://tcgcsv.com/tcgplayer/{category_id}/{group_id}/prices"
        audit_row = {
            "category_id": category_id,
            "group_id": group_id,
            "mapped_products": len(products),
            "url": url,
            "status": "STARTED",
            "result_rows": 0,
            "matched_products": 0,
            "message": "",
        }
        try:
            response = client.get(url, timeout=60)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            prices = extract_rows(response.json())
            audit_row["result_rows"] = len(prices)
            by_pid: dict[str, list[dict[str, Any]]] = {}
            for price_row in prices:
                pid = str(price_row.get("productId") or price_row.get("product_id") or "")
                if pid:
                    by_pid.setdefault(pid, []).append(price_row)

            for product in products:
                pid = product["tcgplayer_product_id"]
                chosen = select_price(by_pid.get(pid, []))
                if chosen is None:
                    continue
                market = as_float(chosen.get("marketPrice") or chosen.get("market_price"))
                low = as_float(chosen.get("lowPrice") or chosen.get("low_price"))
                mid = as_float(chosen.get("midPrice") or chosen.get("mid_price"))
                high = as_float(chosen.get("highPrice") or chosen.get("high_price"))
                direct_low = as_float(chosen.get("directLowPrice") or chosen.get("direct_low_price"))
                selected = market if market is not None else mid if mid is not None else low
                if selected is None:
                    continue
                method = "market_price" if market is not None else "mid_price" if mid is not None else "low_price"
                quality = 100 - (0 if market is not None else 30) - (0 if low is not None else 5)
                output.append({
                    "observation_id": f"{run_id}:{product['investment_product_id']}",
                    "run_id": run_id,
                    "observation_date": observation_date,
                    "collected_at_utc": collected_at,
                    "investment_product_id": product["investment_product_id"],
                    "tcgplayer_product_id": pid,
                    "tcgcsv_category_id": category_id,
                    "tcgcsv_group_id": group_id,
                    "source_product_name": product["source_product_name"],
                    "sub_type_name": chosen.get("subTypeName") or chosen.get("sub_type_name") or "",
                    "market_price": market if market is not None else "",
                    "low_price": low if low is not None else "",
                    "mid_price": mid if mid is not None else "",
                    "high_price": high if high is not None else "",
                    "direct_low_price": direct_low if direct_low is not None else "",
                    "selected_price": selected,
                    "selection_method": method,
                    "price_data_quality": max(0, quality),
                    "source_name": "tcgcsv_live",
                })
                audit_row["matched_products"] += 1
            audit_row["status"] = "PASS"
        except Exception as exc:
            audit_row["status"] = "FAILED"
            audit_row["message"] = str(exc)
        audit.append(audit_row)
        print(f"[{index}/{len(grouped)}] group {group_id}: {audit_row['status']} matched={audit_row['matched_products']}")
        time.sleep(max(0.0, sleep_seconds))

    return output, audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect current TCGCSV prices for confirmed Phase 11E.7 identities.")
    parser.add_argument("--product-map", type=Path, default=PRODUCT_MAP)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--sleep-seconds", type=float, default=0.10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = read_csv(args.product_map.resolve())
    groups = {(row["tcgcsv_category_id"], row["tcgcsv_group_id"]) for row in rows}
    summary = {
        "status": "DRY_RUN" if args.dry_run else "STARTING",
        "live_api_called": False,
        "product_map_rows": len(rows),
        "unique_group_count": len(groups),
        "confirmed_only": all(row.get("discovery_status") == "TCGCSV_ID_CONFIRMED" for row in rows),
    }
    if len(rows) != 871 or not summary["confirmed_only"]:
        summary["status"] = "FAILED"
        summary["reason"] = "Confirmed product map must contain exactly 871 confirmed identities."
        print(json.dumps(summary, indent=2))
        return 2

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        (output_root / "current_price_collection_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 0

    observations, audit = collect(rows, args.sleep_seconds)
    write_csv(output_root / "tcgcsv_current_price_observations.csv", observations)
    audit_path = output_root / "tcgcsv_current_price_group_audit.csv"
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["category_id", "group_id", "mapped_products", "url", "status", "result_rows", "matched_products", "message"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit)

    summary.update({
        "status": "PASS" if observations else "INCOMPLETE",
        "live_api_called": True,
        "observation_rows": len(observations),
        "products_with_current_price": len({row["investment_product_id"] for row in observations}),
        "groups_passed": sum(row["status"] == "PASS" for row in audit),
        "groups_failed": sum(row["status"] == "FAILED" for row in audit),
    })
    (output_root / "current_price_collection_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if observations else 2


if __name__ == "__main__":
    raise SystemExit(main())
