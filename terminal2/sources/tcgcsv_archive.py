from __future__ import annotations

from pathlib import Path
import csv
import json
import time
import urllib.request

import pandas as pd

from terminal2.sources.archive_utils import extract_7z_archive

from terminal2.config import (
    ARCHIVE_CACHE_DIR,
    ARCHIVE_EXTRACT_DIR,
    TCGCSV_ARCHIVE_BASE_URL,
    USER_AGENT,
)
from terminal2.db.loaders import load_products_df, insert_price_observations


def month_starts(start_date: str, end_date: str | None = None):
    start = pd.to_datetime(start_date).date()
    end = pd.to_datetime(end_date).date() if end_date else pd.Timestamp.now("UTC").date()
    dates = [start]
    cur = (pd.Timestamp(start).to_period("M") + 1).to_timestamp().date()
    while cur <= end:
        dates.append(cur)
        cur = (pd.Timestamp(cur).to_period("M") + 1).to_timestamp().date()
    return [d.isoformat() for d in dates]


def archive_url(snapshot_date):
    return f"{TCGCSV_ARCHIVE_BASE_URL}/prices-{snapshot_date}.ppmd.7z"


def archive_file(snapshot_date):
    return Path(ARCHIVE_CACHE_DIR) / f"prices-{snapshot_date}.ppmd.7z"


def extracted_root(snapshot_date):
    return Path(ARCHIVE_EXTRACT_DIR) / snapshot_date


def download_archive(snapshot_date, force=False):
    ARCHIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = archive_file(snapshot_date)
    if out.exists() and out.stat().st_size > 0 and not force:
        return out, "cached"

    req = urllib.request.Request(
        archive_url(snapshot_date),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/octet-stream,*/*;q=0.8",
            "Referer": "https://tcgcsv.com/faq",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        out.write_bytes(response.read())
    return out, "downloaded"


def extract_archive(snapshot_date, force=False):
    root = extracted_root(snapshot_date)
    date_folder = root / snapshot_date
    if date_folder.exists() and not force:
        return date_folder, "cached"

    extract_7z_archive(
        archive_file(snapshot_date),
        root,
        force=force,
    )
    return date_folder if date_folder.exists() else root, "extracted"


def parse_prices_file(path: Path):
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    if raw[0] in "[{":
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("results", [])
        return data if isinstance(data, list) else []

    delimiter = "\t" if "\t" in raw.splitlines()[0] else ","
    return list(csv.DictReader(raw.splitlines(), delimiter=delimiter))


def get_first(row, names):
    for n in names:
        if n in row and row[n] not in [None, "", "null"]:
            return row[n]
    return None


def as_float(v):
    try:
        if v in [None, "", "null"]:
            return None
        return float(v)
    except Exception:
        return None


def ingest_snapshot(snapshot_date: str, force_download=False, force_extract=False):
    products = load_products_df()
    if products.empty:
        raise RuntimeError("No products in SQLite. Run terminal2_sync_products.py first.")

    _archive, download_status = download_archive(snapshot_date, force=force_download)
    root, extract_status = extract_archive(snapshot_date, force=force_extract)

    rows = []
    files_checked = 0

    for (category_id, group_id), group in products.groupby(["tcgcsv_category_id", "tcgcsv_group_id"]):
        price_file = root / str(category_id) / str(group_id) / "prices"
        if not price_file.exists():
            continue

        files_checked += 1
        price_rows = parse_prices_file(price_file)
        by_product = {}
        for pr in price_rows:
            pid = str(get_first(pr, ["productId", "product_id", "productID"]))
            if pid and pid != "None":
                by_product.setdefault(pid, []).append(pr)

        for _, product in group.iterrows():
            pid = str(product["tcgplayer_product_id"])
            matches = by_product.get(pid, [])
            if not matches:
                continue

            chosen = None
            for m in matches:
                subtype = str(get_first(m, ["subTypeName", "sub_type_name"]) or "").lower()
                if subtype in ["normal", ""]:
                    chosen = m
                    break
            if chosen is None:
                chosen = matches[0]

            market = as_float(get_first(chosen, ["marketPrice", "market_price"]))
            low = as_float(get_first(chosen, ["lowPrice", "low_price"]))
            mid = as_float(get_first(chosen, ["midPrice", "mid_price"]))
            high = as_float(get_first(chosen, ["highPrice", "high_price"]))
            price = market or mid or low
            if not price:
                continue

            rows.append({
                "observation_date": snapshot_date,
                "investment_product_id": product["investment_product_id"],
                "tcgplayer_product_id": pid,
                "price_source": "tcgcsv_archive",
                "market_price": round(float(price), 2),
                "low_price": round(float(low), 2) if low else None,
                "mid_price": round(float(mid), 2) if mid else None,
                "high_price": round(float(high), 2) if high else None,
                "price_data_quality": 90,
                "raw_payload": json.dumps(chosen),
            })

    count = insert_price_observations(rows, source_run_id=f"tcgcsv_archive_{snapshot_date}")
    return {
        "snapshot_date": snapshot_date,
        "download_status": download_status,
        "extract_status": extract_status,
        "files_checked": files_checked,
        "rows_inserted": count,
    }


def backfill_monthly(start_date: str, end_date: str | None = None, sleep_seconds=0.25):
    dates = month_starts(start_date, end_date)
    audit = []
    for d in dates:
        print(f"Processing {d}")
        try:
            result = ingest_snapshot(d)
            result["status"] = "success"
        except Exception as exc:
            result = {"snapshot_date": d, "status": "failed", "message": str(exc)}
            print(f"Failed {d}: {exc}")
        audit.append(result)
        time.sleep(sleep_seconds)
    return pd.DataFrame(audit)
