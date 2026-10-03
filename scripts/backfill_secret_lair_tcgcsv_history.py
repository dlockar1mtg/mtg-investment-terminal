"""Build and extend the Secret Lair weekly TCGplayer price history from TCGCSV archives.

TCGCSV publishes a daily archive of every TCGplayer price since 2024-02-08
(https://tcgcsv.com/archive/tcgplayer/prices-YYYY-MM-DD.ppmd.7z). This script takes one
archive per week (Mondays by default), extracts only the Secret Lair groups named in the
approved product map, and appends one row per mapped product and sub-type to a committed
CSV. Dates already present are skipped, so it resumes across runs and later only adds new
weeks. The history lives in the repository so the cloud can read it back.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARCHIVE_BASE_URL = "https://tcgcsv.com/archive/tcgplayer"
FIRST_ARCHIVE_DATE = date(2024, 2, 8)
CATEGORY_ID = "1"
DEFAULT_MAP = ROOT / "docs" / "phase_8" / "secret_lair" / "secret_lair_v1_tcg_current_price_status.csv"
DEFAULT_OUTPUT = ROOT / "data" / "history" / "tcgcsv_weekly" / "secret_lair_weekly_prices.csv"
FIELDS = [
    "snapshot_date", "secret_lair_id", "tcgplayer_product_id", "tcgcsv_group_id", "sub_type",
    "market_price", "low_price", "mid_price", "high_price", "direct_low_price",
]
USER_AGENT = "UIP-MTG-history/1.0 (+https://github.com/dlockar1mtg/mtg-investment-terminal)"


def weekly_dates(start: date, end: date, weekday: int = 0) -> list[date]:
    """Every given weekday (Monday = 0) from start to end inclusive, never before the first archive."""
    first = max(start, FIRST_ARCHIVE_DATE)
    first += timedelta(days=(weekday - first.weekday()) % 7)
    out, current = [], first
    while current <= end:
        out.append(current)
        current += timedelta(days=7)
    return out


def load_map(path: Path) -> dict[str, dict[str, str]]:
    """tcgplayer_product_id -> {secret_lair_id, tcgcsv_group_id} from the approved map."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    mapping = {}
    for row in rows:
        product = str(row.get("tcgplayer_product_id") or "").strip()
        group = str(row.get("tcgcsv_group_id") or "").strip()
        if product.isdigit() and group.isdigit():
            mapping[product] = {"secret_lair_id": row["secret_lair_id"].strip(), "tcgcsv_group_id": group}
    if not mapping:
        raise ValueError(f"no usable rows in {path}")
    return mapping


def existing_dates(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["snapshot_date"] for row in csv.DictReader(handle)}


def _number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if number != number or number <= 0 else f"{number:.2f}"


def select_rows(snapshot: str, group: str, results: Iterable[dict], mapping: dict[str, dict[str, str]]) -> list[dict]:
    rows = []
    for item in results:
        product = str(item.get("productId") or "").strip()
        target = mapping.get(product)
        if not target or target["tcgcsv_group_id"] != group:
            continue
        rows.append({
            "snapshot_date": snapshot,
            "secret_lair_id": target["secret_lair_id"],
            "tcgplayer_product_id": product,
            "tcgcsv_group_id": group,
            "sub_type": str(item.get("subTypeName") or ""),
            "market_price": _number(item.get("marketPrice")),
            "low_price": _number(item.get("lowPrice")),
            "mid_price": _number(item.get("midPrice")),
            "high_price": _number(item.get("highPrice")),
            "direct_low_price": _number(item.get("directLowPrice")),
        })
    return rows


def _download(url: str, destination: Path, retries: int = 3, pause: float = 5.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            return
        except Exception:  # noqa: BLE001 - retried, then re-raised
            if attempt == retries:
                raise
            time.sleep(pause * attempt)


def snapshot_rows(
    snapshot: date,
    groups: set[str],
    mapping: dict[str, dict[str, str]],
    download: Callable[[str, Path], None] = _download,
) -> list[dict]:
    import py7zr

    from terminal2.sources.archive_utils import validate_archive_members

    stamp = snapshot.isoformat()
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / f"prices-{stamp}.ppmd.7z"
        download(f"{ARCHIVE_BASE_URL}/prices-{stamp}.ppmd.7z", archive)
        wanted = {f"{stamp}/{CATEGORY_ID}/{group}/prices" for group in sorted(groups)}
        with py7zr.SevenZipFile(archive, "r") as handle:
            names = handle.getnames()
            validate_archive_members(names)  # the repository's path-safety check
            targets = [name for name in names if name.replace("\\", "/") in wanted]
            if targets:
                handle.extract(path=Path(work) / "x", targets=targets)
        rows = []
        for group in sorted(groups):
            path = Path(work) / "x" / stamp / CATEGORY_ID / group / "prices"
            if not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
            results = payload.get("results", []) if isinstance(payload, dict) else payload
            rows.extend(select_rows(stamp, group, results, mapping))
        return rows


def append_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.is_file()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None, download: Callable[[str, Path], None] = _download) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", type=date.fromisoformat, default=FIRST_ARCHIVE_DATE)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--max-snapshots", type=int, default=0, help="stop after this many new weeks (0 = no limit)")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    mapping = load_map(args.map)
    groups = {target["tcgcsv_group_id"] for target in mapping.values()}
    done = existing_dates(args.output)
    todo = [d for d in weekly_dates(args.start, args.end) if d.isoformat() not in done]
    if args.max_snapshots:
        todo = todo[: args.max_snapshots]
    print(f"{len(mapping)} mapped products in {len(groups)} groups; {len(done)} weeks already stored; {len(todo)} to fetch")
    failures = []
    for snapshot in todo:
        try:
            rows = snapshot_rows(snapshot, groups, mapping, download)
        except Exception as exc:  # noqa: BLE001 - recorded, run continues
            failures.append(f"{snapshot}: {type(exc).__name__}: {exc}")
            print(f"  {snapshot}: FAILED {type(exc).__name__}")
            continue
        append_rows(args.output, rows)
        priced = len({r["secret_lair_id"] for r in rows if r["market_price"]})
        print(f"  {snapshot}: {len(rows)} rows, {priced} products with a market price")
        time.sleep(args.sleep_seconds)
    if failures:
        print("FAILED SNAPSHOTS:\n" + "\n".join(failures))
    return 1 if failures and len(failures) == len(todo) else 0


if __name__ == "__main__":
    raise SystemExit(main())
