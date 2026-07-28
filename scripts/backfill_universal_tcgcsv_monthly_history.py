from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ROUTING_MATRIX = (
    ROOT / "data/operations/mtg_universal_history_completion/"
    "universal_history_routing_matrix.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_universal_history_completion/archive"
)
CACHE = ROOT / "data/cache/mtg_universal_history_completion"
EXTRACT = CACHE / "extracted"
BASE_URL = "https://tcgcsv.com/archive/tcgplayer"
ARCHIVE_START = "2024-02-08"

from terminal2.sources.archive_utils import extract_7z_archive

OBS_FIELDS = [
    "observation_id", "run_id", "observation_date", "collected_at_utc",
    "universal_mtg_product_id", "canonical_product_name", "product_class",
    "tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id",
    "sub_type_name", "market_price", "low_price", "mid_price", "high_price",
    "direct_low_price", "selected_price", "selection_method",
    "price_data_quality", "source_name",
]
GROUP_AUDIT_FIELDS = [
    "snapshot_date", "tcgcsv_category_id", "tcgcsv_group_id",
    "eligible_products", "price_file_found", "price_record_count",
    "matched_products", "rows_created", "status", "message",
]
SNAPSHOT_AUDIT_FIELDS = [
    "snapshot_date", "status", "download_status", "extract_status",
    "eligible_products", "group_pairs_requested", "group_files_found",
    "group_files_missing", "matched_products", "rows_created", "message",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
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


def download(
    snapshot_date: str,
    force: bool,
    retries: int,
    retry_seconds: float,
) -> tuple[Path, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = archive_file(snapshot_date)
    if target.is_file() and target.stat().st_size > 0 and not force:
        return target, "cached"

    part = target.with_suffix(target.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                archive_url(snapshot_date),
                headers={
                    "User-Agent": (
                        "MTGInvestmentTerminal/11E.8 "
                        "(universal-monthly-history; personal use)"
                    ),
                    "Accept": "application/octet-stream,*/*;q=0.8",
                    "Referer": "https://tcgcsv.com/faq",
                },
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                part.write_bytes(response.read())
            if part.stat().st_size <= 0:
                raise RuntimeError("Downloaded archive is empty")
            part.replace(target)
            return target, "downloaded"
        except Exception as exc:
            last_error = exc
            part.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(max(0.0, retry_seconds * attempt))
    raise RuntimeError(
        f"Archive download failed after {retries} attempts: {last_error}"
    )


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
        subtype = str(
            row.get("subTypeName") or row.get("sub_type_name") or ""
        ).casefold()
        if subtype in ("normal", ""):
            return row
    return rows[0]


def eligible_products(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        row for row in rows
        if str(row.get("tcgcsv_archive_eligible") or "").casefold() == "true"
        and str(row.get("tcgplayer_product_id") or "").strip()
        and str(row.get("tcgcsv_category_id") or "").strip()
        and str(row.get("tcgcsv_group_id") or "").strip()
    ]


def group_products(
    products: list[dict[str, str]],
) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in products:
        grouped[
            (
                str(row["tcgcsv_category_id"]).strip(),
                str(row["tcgcsv_group_id"]).strip(),
            )
        ].append(row)
    return grouped


def locate_price_file(
    root: Path,
    snapshot_date: str,
    category_id: str,
    group_id: str,
) -> Path | None:
    candidates = [
        root / category_id / group_id / "prices",
        extracted_root(snapshot_date)
        / snapshot_date / category_id / group_id / "prices",
        extracted_root(snapshot_date) / category_id / group_id / "prices",
    ]
    return next((path for path in candidates if path.is_file()), None)


def process_group(
    snapshot_date: str,
    root: Path,
    category_id: str,
    group_id: str,
    products: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audit = {
        "snapshot_date": snapshot_date,
        "tcgcsv_category_id": category_id,
        "tcgcsv_group_id": group_id,
        "eligible_products": len(products),
        "price_file_found": False,
        "price_record_count": 0,
        "matched_products": 0,
        "rows_created": 0,
        "status": "STARTED",
        "message": "",
    }
    try:
        price_file = locate_price_file(
            root, snapshot_date, category_id, group_id
        )
        if price_file is None:
            audit["status"] = "NO_GROUP_PRICE_FILE"
            return [], audit

        audit["price_file_found"] = True
        price_rows = parse_price_file(price_file)
        audit["price_record_count"] = len(price_rows)
        by_pid: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in price_rows:
            pid = str(
                row.get("productId")
                or row.get("product_id")
                or row.get("productID")
                or ""
            )
            if pid:
                by_pid[pid].append(row)

        now = datetime.now(timezone.utc)
        run_id = f"tcgcsv-universal-archive-{snapshot_date}"
        output: list[dict[str, Any]] = []
        for product in products:
            chosen = select_price(
                by_pid.get(str(product["tcgplayer_product_id"]), [])
            )
            if chosen is None:
                continue
            market = number(chosen.get("marketPrice") or chosen.get("market_price"))
            low = number(chosen.get("lowPrice") or chosen.get("low_price"))
            mid = number(chosen.get("midPrice") or chosen.get("mid_price"))
            high = number(chosen.get("highPrice") or chosen.get("high_price"))
            direct_low = number(
                chosen.get("directLowPrice")
                or chosen.get("direct_low_price")
            )
            selected = (
                market if market is not None
                else mid if mid is not None
                else low
            )
            if selected is None:
                continue
            method = (
                "market_price" if market is not None
                else "mid_price" if mid is not None
                else "low_price"
            )
            uid = product["universal_mtg_product_id"]
            output.append({
                "observation_id": f"{run_id}:{uid}",
                "run_id": run_id,
                "observation_date": snapshot_date,
                "collected_at_utc": now.isoformat(),
                "universal_mtg_product_id": uid,
                "canonical_product_name": product["canonical_product_name"],
                "product_class": product["product_class"],
                "tcgplayer_product_id": product["tcgplayer_product_id"],
                "tcgcsv_category_id": category_id,
                "tcgcsv_group_id": group_id,
                "sub_type_name": (
                    chosen.get("subTypeName")
                    or chosen.get("sub_type_name")
                    or ""
                ),
                "market_price": market if market is not None else "",
                "low_price": low if low is not None else "",
                "mid_price": mid if mid is not None else "",
                "high_price": high if high is not None else "",
                "direct_low_price": (
                    direct_low if direct_low is not None else ""
                ),
                "selected_price": selected,
                "selection_method": method,
                "price_data_quality": 90 if market is not None else 75,
                "source_name": "tcgcsv_archive_monthly",
            })
        audit["matched_products"] = len({
            row["universal_mtg_product_id"] for row in output
        })
        audit["rows_created"] = len(output)
        audit["status"] = "PASS"
        return output, audit
    except Exception as exc:
        audit["status"] = "FAILED"
        audit["message"] = str(exc)
        return [], audit


def merge_by_key(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in [*existing, *incoming]:
        key = tuple(str(row.get(field) or "") for field in key_fields)
        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: tuple(str(row.get(field) or "") for field in key_fields),
    )


def process_snapshot(
    snapshot_date: str,
    grouped: dict[tuple[str, str], list[dict[str, str]]],
    force_download: bool,
    force_extract: bool,
    retries: int,
    retry_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    snapshot_audit = {
        "snapshot_date": snapshot_date,
        "status": "STARTED",
        "download_status": "",
        "extract_status": "",
        "eligible_products": sum(len(rows) for rows in grouped.values()),
        "group_pairs_requested": len(grouped),
        "group_files_found": 0,
        "group_files_missing": 0,
        "matched_products": 0,
        "rows_created": 0,
        "message": "",
    }
    try:
        _, snapshot_audit["download_status"] = download(
            snapshot_date, force_download, retries, retry_seconds
        )
        root, snapshot_audit["extract_status"] = extract(
            snapshot_date, force_extract
        )
        observations: list[dict[str, Any]] = []
        group_audits: list[dict[str, Any]] = []
        for (category_id, group_id), products in sorted(grouped.items()):
            rows, audit = process_group(
                snapshot_date,
                root,
                category_id,
                group_id,
                products,
            )
            observations.extend(rows)
            group_audits.append(audit)

        snapshot_audit["group_files_found"] = sum(
            audit["price_file_found"] is True for audit in group_audits
        )
        snapshot_audit["group_files_missing"] = sum(
            audit["status"] == "NO_GROUP_PRICE_FILE"
            for audit in group_audits
        )
        snapshot_audit["matched_products"] = len({
            row["universal_mtg_product_id"] for row in observations
        })
        snapshot_audit["rows_created"] = len(observations)
        failed_groups = [
            audit for audit in group_audits if audit["status"] == "FAILED"
        ]
        snapshot_audit["status"] = (
            "PASS" if not failed_groups else "INCOMPLETE"
        )
        return observations, group_audits, snapshot_audit
    except Exception as exc:
        snapshot_audit["status"] = "FAILED"
        snapshot_audit["message"] = str(exc)
        return [], [], snapshot_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill monthly TCGCSV archive history for all governed "
            "archive-eligible MTG products."
        )
    )
    parser.add_argument("--routing-matrix", type=Path, default=ROUTING_MATRIX)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--start", default=ARCHIVE_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-snapshots", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument("--keep-archives", action="store_true")
    parser.add_argument("--download-retries", type=int, default=3)
    parser.add_argument("--retry-seconds", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    products = eligible_products(read_csv(args.routing_matrix.resolve()))
    grouped = group_products(products)
    if len(products) != 1039:
        raise SystemExit(
            f"Expected 1039 archive-eligible products; found {len(products)}."
        )
    if len(grouped) != 168:
        raise SystemExit(
            f"Expected 168 archive category/group pairs; found {len(grouped)}."
        )

    dates = month_starts(args.start, args.end)
    if args.max_snapshots:
        dates = dates[:max(0, args.max_snapshots)]

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "universal_archive_backfill_summary.json"
    summary = {
        "status": "DRY_RUN" if args.dry_run else "STARTING",
        "live_source_called": False,
        "archive_eligible_products": len(products),
        "archive_group_pairs": len(grouped),
        "snapshot_count": len(dates),
        "snapshot_dates": dates,
        "archive_start_limit": ARCHIVE_START,
    }
    if args.dry_run:
        summary_path.write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2))
        return 0

    new_observations: list[dict[str, Any]] = []
    new_group_audits: list[dict[str, Any]] = []
    new_snapshot_audits: list[dict[str, Any]] = []
    for index, snapshot_date in enumerate(dates, start=1):
        rows, group_audits, snapshot_audit = process_snapshot(
            snapshot_date,
            grouped,
            args.force_download,
            args.force_extract,
            max(1, args.download_retries),
            args.retry_seconds,
        )
        new_observations.extend(rows)
        new_group_audits.extend(group_audits)
        new_snapshot_audits.append(snapshot_audit)
        print(
            f"[{index}/{len(dates)}] {snapshot_date}: "
            f"{snapshot_audit['status']} rows={snapshot_audit['rows_created']} "
            f"groups={snapshot_audit['group_files_found']}/"
            f"{snapshot_audit['group_pairs_requested']}"
        )
        if (
            not args.keep_archives
            and snapshot_audit["status"] != "FAILED"
        ):
            archive_file(snapshot_date).unlink(missing_ok=True)
            shutil.rmtree(extracted_root(snapshot_date), ignore_errors=True)
        time.sleep(max(0.0, args.sleep_seconds))

    observations_path = (
        output_root / "universal_tcgcsv_monthly_archive_observations.csv"
    )
    group_audit_path = (
        output_root / "universal_tcgcsv_monthly_group_audit.csv"
    )
    snapshot_audit_path = (
        output_root / "universal_tcgcsv_monthly_snapshot_audit.csv"
    )

    observations = merge_by_key(
        read_csv(observations_path),
        new_observations,
        ("universal_mtg_product_id", "observation_date"),
    )
    group_audits = merge_by_key(
        read_csv(group_audit_path),
        new_group_audits,
        ("snapshot_date", "tcgcsv_category_id", "tcgcsv_group_id"),
    )
    snapshot_audits = merge_by_key(
        read_csv(snapshot_audit_path),
        new_snapshot_audits,
        ("snapshot_date",),
    )

    write_csv(observations_path, observations, OBS_FIELDS)
    write_csv(group_audit_path, group_audits, GROUP_AUDIT_FIELDS)
    write_csv(snapshot_audit_path, snapshot_audits, SNAPSHOT_AUDIT_FIELDS)

    incomplete = [
        row for row in snapshot_audits
        if row["status"] not in {"PASS"}
    ]
    summary.update({
        "status": "PASS" if not incomplete else "INCOMPLETE",
        "live_source_called": True,
        "observation_rows": len(observations),
        "products_with_archive_history": len({
            row["universal_mtg_product_id"] for row in observations
        }),
        "distinct_observation_dates": len({
            row["observation_date"] for row in observations
        }),
        "persisted_snapshot_count": len(snapshot_audits),
        "snapshots_passed": sum(
            row["status"] == "PASS" for row in snapshot_audits
        ),
        "snapshots_incomplete": sum(
            row["status"] == "INCOMPLETE" for row in snapshot_audits
        ),
        "snapshots_failed": sum(
            row["status"] == "FAILED" for row in snapshot_audits
        ),
        "observation_keys_unique": len(observations) == len({
            (
                row["universal_mtg_product_id"],
                row["observation_date"],
            )
            for row in observations
        }),
        "snapshot_dates_unique": len(snapshot_audits) == len({
            row["snapshot_date"] for row in snapshot_audits
        }),
    })
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
