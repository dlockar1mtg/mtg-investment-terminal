from __future__ import annotations

from datetime import date
from pathlib import Path
import argparse
import csv
import json
import sys
import time
import urllib.request

import pandas as pd

from terminal2.sources.archive_utils import extract_7z_archive

from config import (
    PRODUCT_MASTER_FILE,
    HISTORICAL_IMPORT_FILE,
    TCGCSV_ARCHIVE_START_DATE,
    TCGCSV_ARCHIVE_DIR,
    TCGCSV_ARCHIVE_EXTRACT_DIR,
    TCGCSV_MONTHLY_BACKFILL_AUDIT_FILE,
    TCGCSV_ARCHIVE_BASE_URL,
)


def month_starts(start_date: str, end_date: str | None = None):
    start = pd.to_datetime(start_date).date()
    if end_date:
        end = pd.to_datetime(end_date).date()
    else:
        end = pd.Timestamp.now('UTC').date()

    # Use the actual archive start date for the first month, then first day of each month.
    dates = [start]
    first_next_month = (pd.Timestamp(start).to_period("M") + 1).to_timestamp().date()

    current = first_next_month
    while current <= end:
        dates.append(current)
        current = (pd.Timestamp(current).to_period("M") + 1).to_timestamp().date()

    return [d.isoformat() for d in dates]


def load_approved_products():
    master = pd.read_csv(PRODUCT_MASTER_FILE, dtype=str)
    approved = master[master["approval_status"].astype(str).str.lower() == "approved"].copy()
    if approved.empty:
        raise RuntimeError("No approved products found. Run python run.py first.")

    approved["approved_tcgplayer_product_id"] = approved["approved_tcgplayer_product_id"].astype(str)
    approved["tcgcsv_category_id"] = approved["tcgcsv_category_id"].astype(str)
    approved["tcgcsv_group_id"] = approved["tcgcsv_group_id"].astype(str)

    return approved


def archive_url(snapshot_date: str) -> str:
    return f"{TCGCSV_ARCHIVE_BASE_URL}/prices-{snapshot_date}.ppmd.7z"


def archive_file(snapshot_date: str) -> Path:
    return Path(TCGCSV_ARCHIVE_DIR) / f"prices-{snapshot_date}.ppmd.7z"


def extract_dir(snapshot_date: str) -> Path:
    return Path(TCGCSV_ARCHIVE_EXTRACT_DIR) / snapshot_date



def download_archive(snapshot_date: str, force=False):
    Path(TCGCSV_ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)
    out = archive_file(snapshot_date)

    if out.exists() and out.stat().st_size > 0 and not force:
        return out, "cached"

    url = archive_url(snapshot_date)
    print(f"Downloading {url}")

    # TCGCSV FAQ requests a clearly identifiable User-Agent for automated access.
    # Python's default urllib User-Agent can be blocked and may return 401.
    headers = {
        "User-Agent": "MTGInvestmentTerminal/13.2 (historical archive backfill; personal use)",
        "Accept": "application/octet-stream,*/*;q=0.8",
        "Referer": "https://tcgcsv.com/faq",
    }

    request = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
    except Exception as exc:
        # Provide a more actionable error than a raw urllib 401.
        if "HTTP Error 401" in str(exc):
            raise RuntimeError(
                "TCGCSV returned 401 Unauthorized. The script now sends a User-Agent, "
                "so if this persists, try opening the archive URL in your browser. "
                "If the browser also fails, TCGCSV may have temporarily restricted archive access."
            ) from exc
        raise

    out.write_bytes(data)
    return out, "downloaded"

def extract_archive(snapshot_date: str, force=False):
    archive = archive_file(snapshot_date)
    out_dir = extract_dir(snapshot_date)
    expected_date_folder = out_dir / snapshot_date

    if expected_date_folder.exists() and not force:
        return expected_date_folder, "cached"

    print(f"Extracting {archive.name} with py7zr")
    extract_7z_archive(
        archive,
        out_dir,
        force=force,
    )

    if expected_date_folder.exists():
        return expected_date_folder, "extracted"

    return out_dir, "extracted"


def parse_prices_file(path: Path):
    """
    TCGCSV current price endpoint returns JSON with {'results': [...]}.
    Archives appear as files named 'prices'. This parser accepts:
    - JSON object with results
    - JSON list
    - CSV with headers
    - TSV with headers
    """
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []

    # JSON object or array
    if raw[0] in "[{":
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("results", [])
        if isinstance(data, list):
            return data

    # CSV / TSV fallback
    delimiter = "\t" if "\t" in raw.splitlines()[0] else ","
    reader = csv.DictReader(raw.splitlines(), delimiter=delimiter)
    return list(reader)


def get_first(row, names):
    for name in names:
        if name in row and row[name] not in [None, "", "null"]:
            return row[name]
    return None


def as_float(value):
    if value in [None, "", "null"]:
        return None
    try:
        return float(value)
    except Exception:
        return None


def process_snapshot(snapshot_date: str, approved: pd.DataFrame, keep_archives=True, force_download=False, force_extract=False):
    audit = {
        "snapshot_date": snapshot_date,
        "status": "started",
        "download_status": "",
        "extract_status": "",
        "approved_products": len(approved),
        "price_files_checked": 0,
        "rows_created": 0,
        "message": "",
    }

    try:
        _archive, download_status = download_archive(snapshot_date, force=force_download)
        audit["download_status"] = download_status

        root, extract_status = extract_archive(snapshot_date, force=force_extract)
        audit["extract_status"] = extract_status

        rows = []

        # Group approved products by archive category/group path.
        for (category_id, group_id), group in approved.groupby(["tcgcsv_category_id", "tcgcsv_group_id"]):
            price_file = root / str(category_id) / str(group_id) / "prices"

            if not price_file.exists():
                # Sometimes root may already be the date folder or parent folder.
                alt = Path(TCGCSV_ARCHIVE_EXTRACT_DIR) / snapshot_date / snapshot_date / str(category_id) / str(group_id) / "prices"
                if alt.exists():
                    price_file = alt
                else:
                    continue

            audit["price_files_checked"] += 1

            try:
                price_rows = parse_prices_file(price_file)
            except Exception as exc:
                print(f"Could not parse {price_file}: {exc}")
                continue

            by_product = {}
            for pr in price_rows:
                product_id = str(get_first(pr, ["productId", "product_id", "productID"]))
                if product_id and product_id != "None":
                    by_product.setdefault(product_id, []).append(pr)

            for _, product in group.iterrows():
                pid = str(product["approved_tcgplayer_product_id"])
                matches = by_product.get(pid, [])
                if not matches:
                    continue

                # Prefer Normal subtype or first available.
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

                current_price = market or mid or low
                if not current_price:
                    continue

                rows.append({
                    "observation_date": snapshot_date,
                    "investment_product_id": product["investment_product_id"],
                    "tcgplayer_product_id": pid,
                    "box_name": product["box_name"],
                    "set_name": product["set_name"],
                    "current_price": round(float(current_price), 2),
                    "low_price": round(float(low), 2) if low else "",
                    "price_source": "tcgcsv_archive_monthly",
                    "price_data_quality": 90,
                })

        audit["rows_created"] = len(rows)
        audit["status"] = "success"
        return rows, audit

    except Exception as exc:
        audit["status"] = "failed"
        audit["message"] = str(exc)
        print(f"Snapshot failed for {snapshot_date}: {exc}")
        return [], audit


def write_import_file(rows, append=False):
    out = Path(HISTORICAL_IMPORT_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No historical rows created.")
        return df

    if append and out.exists():
        existing = pd.read_csv(out, dtype={"investment_product_id": str, "tcgplayer_product_id": str})
        df = pd.concat([existing, df], ignore_index=True, sort=False)

    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce").dt.date.astype(str)
    df = (
        df.sort_values(["investment_product_id", "observation_date"])
          .drop_duplicates(subset=["investment_product_id", "observation_date"], keep="last")
          .copy()
    )

    df.to_csv(out, index=False)
    print(f"Historical import file written: {out}")
    print(f"Rows: {len(df)}")
    return df


def write_audit(audit_rows):
    out = Path(TCGCSV_MONTHLY_BACKFILL_AUDIT_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(audit_rows)
    df.to_csv(out, index=False)
    print(f"Audit written: {out}")
    return df


def main():
    parser = argparse.ArgumentParser(description="Backfill monthly TCGCSV price archive snapshots.")
    parser.add_argument("--start", default=TCGCSV_ARCHIVE_START_DATE, help="Start date. Default: 2024-02-08")
    parser.add_argument("--end", default=None, help="End date. Default: today UTC")
    parser.add_argument("--append", action="store_true", help="Append to existing historical_price_import.csv")
    parser.add_argument("--force-download", action="store_true", help="Redownload archives even if cached")
    parser.add_argument("--force-extract", action="store_true", help="Re-extract archives even if cached")
    parser.add_argument("--sleep", type=float, default=0.25, help="Seconds to sleep between archive downloads")
    args = parser.parse_args()

    approved = load_approved_products()
    dates = month_starts(args.start, args.end)

    print(f"Approved products: {len(approved)}")
    print(f"Monthly snapshots: {len(dates)}")
    print(f"Dates: {', '.join(dates)}")

    all_rows = []
    audits = []

    for snapshot_date in dates:
        print(f"\nProcessing {snapshot_date}")
        rows, audit = process_snapshot(
            snapshot_date,
            approved,
            force_download=args.force_download,
            force_extract=args.force_extract,
        )
        all_rows.extend(rows)
        audits.append(audit)
        time.sleep(args.sleep)

    write_import_file(all_rows, append=args.append)
    write_audit(audits)

    print("\nNext run:")
    print("python import_historical_prices.py")
    print("python review_historical_database.py")
    print("python run.py")


if __name__ == "__main__":
    main()
