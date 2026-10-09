"""Collect daily TCGplayer prices for sealed booster boxes from TCGCSV's live price files.

Reads the box list (TCGplayer product id and TCGCSV group id per box), fetches each group's
price file once (TCGCSV asks for at most one request per file per 24 hours), keeps the listed
boxes' market, lowest-listing and TCGplayer Direct low prices, overwrites a latest-prices file
and appends to a weekly history on the first successful fetch of each week. The stored history
lets the box models refit as it grows and makes the listing gap testable for boxes.

Partial fetches: when some groups fail, their boxes' previous rows are carried forward into the
latest-prices file unchanged (keeping their original snapshot_date) with stale_carried=true, so
a feed outage never silently drops boxes; the weekly history only ever gets fresh rows. If fewer
than MIN_FRESH_GROUP_SHARE of the groups were fetched, nothing is written and the run exits 1.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOXES = ROOT / "data" / "product_master" / "product_master_model_input.csv"
DEFAULT_DIR = ROOT / "data" / "history" / "boxes"
LIVE_BASE_URL = "https://tcgcsv.com/tcgplayer"
CATEGORY_ID = "1"
USER_AGENT = "UIP-MTG-history/1.0 (+https://github.com/dlockar1mtg/mtg-investment-terminal)"
WEEKLY_FIELDS = ["snapshot_date", "tcgplayer_product_id", "box_name", "tcgcsv_group_id", "sub_type",
                 "market_price", "low_price", "mid_price", "high_price", "direct_low_price"]
FIELDS = WEEKLY_FIELDS + ["stale_carried"]   # latest-prices file: true on rows carried from an earlier day
MIN_FRESH_GROUP_SHARE = 0.95                # below this share of groups fetched, publish nothing


def load_boxes(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    boxes = {}
    for row in rows:
        product = str(row.get("tcgplayer_product_id") or "").strip()
        group = str(row.get("tcgcsv_group_id") or "").strip()
        if product.isdigit() and group.isdigit():
            boxes[product] = {"box_name": (row.get("box_name") or row.get("official_product_name") or "").strip(), "group": group}
    if not boxes:
        raise ValueError(f"no boxes with product and group ids in {path}")
    return boxes


def _number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if number != number or number <= 0 else f"{number:.2f}"


def _fetch_json(url: str, retries: int = 3, pause: float = 5.0):
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except Exception:  # noqa: BLE001 - retried, then re-raised
            if attempt == retries:
                raise
            time.sleep(pause * attempt)


def collect(today: date, boxes, fetch: Callable[[str], object] = _fetch_json, sleep_seconds: float = 0.2):
    """Rows for the listed boxes, and the failures as 'group: error' strings."""
    rows, failures = [], []
    for group in sorted({b["group"] for b in boxes.values()}):
        try:
            payload = fetch(f"{LIVE_BASE_URL}/{CATEGORY_ID}/{group}/prices")
        except Exception as exc:  # noqa: BLE001 - recorded; other groups continue
            failures.append(f"{group}: {type(exc).__name__}")
            continue
        results = payload.get("results", []) if isinstance(payload, dict) else payload
        for item in results or []:
            product = str(item.get("productId") or "").strip()
            box = boxes.get(product)
            if not box or box["group"] != group:
                continue
            rows.append({"snapshot_date": today.isoformat(), "tcgplayer_product_id": product, "box_name": box["box_name"],
                         "tcgcsv_group_id": group, "sub_type": str(item.get("subTypeName") or ""),
                         "market_price": _number(item.get("marketPrice")), "low_price": _number(item.get("lowPrice")),
                         "mid_price": _number(item.get("midPrice")), "high_price": _number(item.get("highPrice")),
                         "direct_low_price": _number(item.get("directLowPrice"))})
        time.sleep(sleep_seconds)
    return rows, failures


def _previous(path: Path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _dates(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["snapshot_date"] for row in csv.DictReader(handle)}


def carry_forward(previous_rows, failed_groups, boxes):
    """Previous latest rows of the listed boxes in groups that failed today, flagged stale_carried."""
    out = []
    for r in previous_rows:
        product, group = str(r.get("tcgplayer_product_id") or "").strip(), str(r.get("tcgcsv_group_id") or "").strip()
        box = boxes.get(product)
        if box and box["group"] == group and group in failed_groups:
            out.append({**{k: r.get(k, "") for k in WEEKLY_FIELDS}, "stale_carried": "true"})
    return out


def _write(path: Path, rows, append: bool, fields=FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file() or not append
    with path.open("a" if append else "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def main(argv=None, fetch: Callable[[str], object] = _fetch_json, today: date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--boxes", type=Path, default=DEFAULT_BOXES)
    parser.add_argument("--segment", default="collector", help="file prefix, e.g. collector")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    args = parser.parse_args(argv)
    day = today or date.today()
    boxes = load_boxes(args.boxes)
    rows, failures = collect(day, boxes, fetch, args.sleep_seconds)
    priced = len({r["tcgplayer_product_id"] for r in rows if r["market_price"]})
    if not priced:
        print(f"BOX FETCH FAILED: no listed box has a market price; failures: {failures}")
        return 1
    groups = {b["group"] for b in boxes.values()}
    failed_groups = {f.split(":", 1)[0] for f in failures}
    fresh_share = 1 - len(failed_groups) / len(groups)
    if fresh_share < MIN_FRESH_GROUP_SHARE:
        print(f"BOX FETCH FAILED: only {len(groups) - len(failed_groups)} of {len(groups)} groups fetched "
              f"({fresh_share:.0%} < {MIN_FRESH_GROUP_SHARE:.0%}); previous files left unchanged. Failures: {', '.join(failures)}")
        return 1
    for r in rows:
        r["stale_carried"] = ""
    latest = args.output_dir / f"{args.segment}_latest_prices.csv"
    weekly = args.output_dir / f"{args.segment}_weekly_prices.csv"
    carried = carry_forward(_previous(latest), failed_groups, boxes)
    _write(latest, rows + carried, append=False)
    monday = day - timedelta(days=day.weekday())
    stored = _dates(weekly)
    extended = not any((monday + timedelta(days=k)).isoformat() in stored for k in range(7))
    if extended:
        _write(weekly, rows, append=True, fields=WEEKLY_FIELDS)
    print(f"{day}: {priced} of {len(boxes)} boxes priced; groups failed {len(failed_groups)} of {len(groups)}; "
          f"{len(carried)} earlier rows carried forward; weekly history {'extended' if extended else 'already has this week'}")
    if failures:
        print("FAILED GROUPS: " + ", ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
