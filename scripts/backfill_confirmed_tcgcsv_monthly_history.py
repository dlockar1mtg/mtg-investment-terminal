from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PRODUCT_MAP = ROOT / "data/operations/mtg_tcgcsv_price_backfill/confirmed_tcgcsv_product_map.csv"
OUTPUT = ROOT / "data/operations/mtg_tcgcsv_price_backfill/archive"
CACHE = ROOT / "data/cache/mtg_tcgcsv_price_backfill"
EXTRACT = ROOT / "data/cache/mtg_tcgcsv_price_backfill/extracted"
BASE_URL = "https://tcgcsv.com/archive/tcgplayer"
ARCHIVE_START = "2024-02-08"

try:
    from terminal2.sources.archive_utils import extract_7z_archive
except ImportError as exc:
    raise RuntimeError("terminal2.sources.archive_utils.extract_7z_archive is required") from exc


OBS_FIELDS = [
    "observation_id", "run_id", "observation_date", "collected_at_utc",
    "investment_product_id", "tcgplayer_product_id", "tcgcsv_category_id",
    "tcgcsv_group_id", "source_product_name", "sub_type_name",
    "market_price", "low_price", "mid_price", "high_price",
    "direct_low_price", "selected_price", "selection_method",
    "price_data_quality", "source_name",
]

AUDIT_FIELDS = [
    "snapshot_date", "status", "download_status", "extract_status",
    "price_file_found", "price_record_count", "matched_products",
    "rows_created", "message",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def month_starts(start: str, end: str | None) -> list[str]:
    start_date = pd.to_datetime(start).date()
    end_date = pd.to_datetime(end).date() if end else pd.Timestamp.now("UTC").date()
    values = [start_date]
    current = (pd.Timestamp(start_date).to_period("M") + 1).to_timestamp().date()
    while current <= end_date:
        values.append(current)
        current = (pd.Timestamp(current).to_period("M") + 1).to_timestamp().date()
    return [value.isoformat() for value in values]


def archive_url(snapshot_date: str) -> str:
    return f"{BASE_URL}/prices-{snapshot_date}.ppmd.7z"


def archive_file(snapshot_date: str) -> Path:
    return CACHE / f"prices-{snapshot_date}.ppmd.7z"


def extracted_root(snapshot_date: str) -> Path:
    return EXTRACT / snapshot_date


def download(snapshot_date: str, force: bool) -> tuple[Path, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = archive_file(snapshot_date)
    if target.is_file() and target.stat().st_size > 0 and not force:
        return target, "cached"

    request = urllib.request.Request(
        archive_url(snapshot_date),
        headers={
            "User-Agent": "MTGInvestmentTerminal/11E.7 (confirmed-monthly-backfill; personal use)",
            "Accept": "application/octet-stream,*/*;q=0.8",
            "Referer": "https://tcgcsv.com/faq",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        target.write_bytes(response.read())
    return target, "downloaded"


def extract(snapshot_date: str, force: bool) -> tuple[Path, str]:
    root = extracted_root(snapshot_date)
    date_folder = root / snapshot_date
    if date_folder.is_dir() and not force:
        return date_folder, "cached"

    extract_7z_archive(archive_file(snapshot_date), root, force=force)
    return (date_folder if date_folder.is_dir() else root), "extracted"


def parse_price_file(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    if raw[0] in "[{":
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload.get("results", [])
        return payload if isinstance(payload, list) else []
    delimiter = "\t" if "\t" in raw.splitlines()[0] else ","
    return list(csv.DictReader(raw.splitlines(), delimiter=delimiter))


def number(value: Any) -> float | None:
    try:
        if value in (None, "", "null"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def select_price(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    for row in rows:
        subtype = str(row.get("subTypeName") or row.get("sub_type_name") or "").casefold()
        if subtype in ("normal", ""):
            return row
    return rows[0]


def process_snapshot(snapshot_date: str, products: list[dict[str, str]], force_download: bool, force_extract: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audit = {
        "snapshot_date": snapshot_date,
        "status": "STARTED",
        "download_status": "",
        "extract_status": "",
        "price_file_found": False,
        "price_record_count": 0,
        "matched_products": 0,
        "rows_created": 0,
        "message": "",
    }
    try:
        _, audit["download_status"] = download(snapshot_date, force_download)
        root, audit["extract_status"] = extract(snapshot_date, force_extract)
        price_file = root / "1" / "2576" / "prices"
        if not price_file.is_file():
            alternate = extracted_root(snapshot_date) / snapshot_date / "1" / "2576" / "prices"
            if alternate.is_file():
                price_file = alternate
        if not price_file.is_file():
            audit["status"] = "NO_GROUP_PRICE_FILE"
            return [], audit

        audit["price_file_found"] = True
        price_rows = parse_price_file(price_file)
        audit["price_record_count"] = len(price_rows)
        by_pid: dict[str, list[dict[str, Any]]] = {}
        for row in price_rows:
            pid = str(row.get("productId") or row.get("product_id") or row.get("productID") or "")
            if pid:
                by_pid.setdefault(pid, []).append(row)

        now = datetime.now(timezone.utc)
        run_id = f"tcgcsv-archive-{snapshot_date}"
        output = []
        for product in products:
            chosen = select_price(by_pid.get(product["tcgplayer_product_id"], []))
            if chosen is None:
                continue
            market = number(chosen.get("marketPrice") or chosen.get("market_price"))
            low = number(chosen.get("lowPrice") or chosen.get("low_price"))
            mid = number(chosen.get("midPrice") or chosen.get("mid_price"))
            high = number(chosen.get("highPrice") or chosen.get("high_price"))
            direct_low = number(chosen.get("directLowPrice") or chosen.get("direct_low_price"))
            selected = market if market is not None else mid if mid is not None else low
            if selected is None:
                continue
            method = "market_price" if market is not None else "mid_price" if mid is not None else "low_price"
            output.append({
                "observation_id": f"{run_id}:{product['investment_product_id']}",
                "run_id": run_id,
                "observation_date": snapshot_date,
                "collected_at_utc": now.isoformat(),
                "investment_product_id": product["investment_product_id"],
                "tcgplayer_product_id": product["tcgplayer_product_id"],
                "tcgcsv_category_id": "1",
                "tcgcsv_group_id": "2576",
                "source_product_name": product["source_product_name"],
                "sub_type_name": chosen.get("subTypeName") or chosen.get("sub_type_name") or "",
                "market_price": market if market is not None else "",
                "low_price": low if low is not None else "",
                "mid_price": mid if mid is not None else "",
                "high_price": high if high is not None else "",
                "direct_low_price": direct_low if direct_low is not None else "",
                "selected_price": selected,
                "selection_method": method,
                "price_data_quality": 90 if market is not None else 75,
                "source_name": "tcgcsv_archive_monthly",
            })
        audit["matched_products"] = len({row["investment_product_id"] for row in output})
        audit["rows_created"] = len(output)
        audit["status"] = "PASS"
        return output, audit
    except Exception as exc:
        audit["status"] = "FAILED"
        audit["message"] = str(exc)
        return [], audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill monthly TCGCSV archives for 871 confirmed Secret Lair identities.")
    parser.add_argument("--product-map", type=Path, default=PRODUCT_MAP)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--start", default=ARCHIVE_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-snapshots", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument("--keep-archives", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    products = read_csv(args.product_map.resolve())
    if len(products) != 871 or any(row.get("discovery_status") != "TCGCSV_ID_CONFIRMED" for row in products):
        raise SystemExit("Confirmed product map must contain exactly 871 confirmed products.")

    dates = month_starts(args.start, args.end)
    if args.max_snapshots:
        dates = dates[:max(0, args.max_snapshots)]

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "DRY_RUN" if args.dry_run else "STARTING",
        "live_source_called": False,
        "confirmed_product_rows": len(products),
        "snapshot_count": len(dates),
        "snapshot_dates": dates,
        "archive_start_limit": ARCHIVE_START,
    }
    if args.dry_run:
        (output_root / "tcgcsv_archive_backfill_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 0

    all_rows = []
    audits = []
    for index, snapshot_date in enumerate(dates, start=1):
        rows, audit = process_snapshot(
            snapshot_date,
            products,
            args.force_download,
            args.force_extract,
        )
        all_rows.extend(rows)
        audits.append(audit)
        print(f"[{index}/{len(dates)}] {snapshot_date}: {audit['status']} rows={audit['rows_created']}")
        if not args.keep_archives and audit["status"] != "FAILED":
            archive_file(snapshot_date).unlink(missing_ok=True)
            shutil.rmtree(extracted_root(snapshot_date), ignore_errors=True)
        time.sleep(max(0.0, args.sleep_seconds))

    deduped = {}
    for row in all_rows:
        deduped[(row["investment_product_id"], row["observation_date"])] = row
    rows = sorted(deduped.values(), key=lambda row: (row["investment_product_id"], row["observation_date"]))

    write_csv(output_root / "tcgcsv_monthly_archive_observations.csv", rows, OBS_FIELDS)
    write_csv(output_root / "tcgcsv_monthly_archive_audit.csv", audits, AUDIT_FIELDS)

    summary.update({
        "status": "PASS" if all(row["status"] == "PASS" for row in audits) else "INCOMPLETE",
        "live_source_called": True,
        "observation_rows": len(rows),
        "products_with_archive_history": len({row["investment_product_id"] for row in rows}),
        "distinct_observation_dates": len({row["observation_date"] for row in rows}),
        "snapshots_passed": sum(row["status"] == "PASS" for row in audits),
        "snapshots_failed": sum(row["status"] == "FAILED" for row in audits),
        "snapshots_without_group_file": sum(row["status"] == "NO_GROUP_PRICE_FILE" for row in audits),
    })
    (output_root / "tcgcsv_archive_backfill_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())


