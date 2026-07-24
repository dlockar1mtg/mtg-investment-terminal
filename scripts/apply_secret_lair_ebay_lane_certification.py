from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERTIFIER = ROOT / "scripts/certify_secret_lair_ebay_lane.py"
TESTS = ROOT / "tests/test_secret_lair_ebay_lane_certification.py"

CERTIFIER_CONTENT = r'''from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BATCH_PATTERN = re.compile(r"^sealed_secret_lair_(\d{4})_(\d{4})$")
DEFAULT_BATCHES_ROOT = ROOT / "data/validation/phase_10/ebay_matching/batches"
DEFAULT_OUTPUT_ROOT = ROOT / "data/validation/phase_10/ebay_matching/certification"
EXPECTED_START = 0
EXPECTED_END = 972
EXPECTED_PRODUCTS = 973


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def newest_file(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern!r} in {root}")
    return matches[0]


def parse_batch_range(path: Path) -> tuple[int, int]:
    match = BATCH_PATTERN.fullmatch(path.name)
    if not match:
        raise ValueError(f"Invalid Secret Lair batch directory name: {path.name}")
    start, end = (int(value) for value in match.groups())
    if start > end:
        raise ValueError(f"Invalid batch range {start}-{end}")
    return start, end


def discover_batches(batches_root: Path) -> list[tuple[int, int, Path]]:
    batches: list[tuple[int, int, Path]] = []
    for path in batches_root.iterdir():
        if path.is_dir() and BATCH_PATTERN.fullmatch(path.name):
            start, end = parse_batch_range(path)
            batches.append((start, end, path))
    return sorted(batches, key=lambda item: item[0])


def contiguous_ranges(ranges: list[tuple[int, int]]) -> bool:
    if not ranges:
        return False
    return all(current_start == previous_end + 1 for (_, previous_end), (current_start, _) in zip(ranges, ranges[1:]))


def load_audit_module():
    audit_path = ROOT / "scripts/audit_ebay_matching_batch.py"
    spec = importlib.util.spec_from_file_location("audit_ebay_matching_batch", audit_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load audit module from {audit_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accepted_exception_count(rows: list[dict[str, str]], low_score_threshold: float) -> int:
    audit = load_audit_module()
    count = 0
    for row in rows:
        if row.get("match_state") != "ACCEPTED":
            continue
        if audit.flag_row(row, low_score_threshold):
            count += 1
    return count


def cross_product_duplicate_count(rows: list[dict[str, str]]) -> int:
    products_by_item: dict[str, set[str]] = defaultdict(set)
    rows_by_item: Counter[str] = Counter()
    for row in rows:
        if row.get("match_state") != "ACCEPTED":
            continue
        item_id = (row.get("ebay_item_id") or "").strip()
        product_id = (row.get("canonical_product_id") or "").strip()
        if not item_id:
            continue
        products_by_item[item_id].add(product_id)
        rows_by_item[item_id] += 1
    return sum(rows_by_item[item_id] for item_id, products in products_by_item.items() if len(products) > 1)


def certify_batch(start: int, end: int, batch_root: Path, low_score_threshold: float) -> dict[str, Any]:
    summary_path = newest_file(batch_root, "ebay_matching_summary_*.json")
    coverage_path = newest_file(batch_root, "ebay_product_coverage_*.csv")
    listings_path = newest_file(batch_root, "ebay_listing_match_results_*.csv")

    summary = read_json(summary_path)
    coverage = read_csv(coverage_path)
    listings = read_csv(listings_path)

    expected = end - start + 1
    unique_product_ids = len({row.get("canonical_product_id", "") for row in coverage if row.get("canonical_product_id", "")})
    source_errors = sum(
        1
        for row in coverage
        if row.get("coverage_state") == "SOURCE_ERROR" or (row.get("source_error") or "").strip()
    )
    states = Counter(row.get("match_state", "") for row in listings)
    duplicate_product_items = sum(
        group_count - 1
        for group_count in Counter(
            (row.get("canonical_product_id", ""), row.get("ebay_item_id", ""))
            for row in listings
            if (row.get("ebay_item_id") or "").strip()
        ).values()
        if group_count > 1
    )
    accepted_exceptions = accepted_exception_count(listings, low_score_threshold)
    cross_product_duplicates = cross_product_duplicate_count(listings)

    checks = {
        "range_size_matches": len(coverage) == expected,
        "unique_products_match": unique_product_ids == expected,
        "summary_products_match": int(summary.get("products", -1)) == expected,
        "summary_expected_products_match": int(summary.get("expected_products", -1)) == expected,
        "summary_not_aborted": summary.get("aborted_early") is False,
        "source_errors_zero": source_errors == 0,
        "listing_rows_match": int(summary.get("listing_rows", -1)) == len(listings),
        "accepted_rows_match": int(summary.get("accepted_rows", -1)) == states["ACCEPTED"],
        "review_rows_match": int(summary.get("review_rows", -1)) == states["REVIEW"],
        "rejected_rows_match": int(summary.get("rejected_rows", -1)) == states["REJECTED"],
        "duplicate_product_items_zero": duplicate_product_items == 0,
        "accepted_exceptions_zero": accepted_exceptions == 0,
        "cross_product_duplicates_zero": cross_product_duplicates == 0,
    }

    return {
        "batch_key": batch_root.name,
        "start_offset": start,
        "end_offset": end,
        "expected_products": expected,
        "products": len(coverage),
        "unique_product_ids": unique_product_ids,
        "listing_rows": len(listings),
        "accepted_rows": states["ACCEPTED"],
        "review_rows": states["REVIEW"],
        "rejected_rows": states["REJECTED"],
        "source_errors": source_errors,
        "duplicate_product_items": duplicate_product_items,
        "accepted_exception_rows": accepted_exceptions,
        "cross_product_duplicate_rows": cross_product_duplicates,
        "summary_path": str(summary_path.resolve()),
        "coverage_path": str(coverage_path.resolve()),
        "listings_path": str(listings_path.resolve()),
        "checks": checks,
        "status": "CERTIFIED" if all(checks.values()) else "FAILED",
    }


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 10 Secret Lair eBay Matching Lane Certification",
        "",
        f"**Status:** {payload['status']}",
        f"**Certified at (UTC):** {payload['certified_at_utc']}",
        "",
        "## Certified Scope",
        "",
        f"- Operational English Secret Lair products: {payload['products']}",
        f"- Covered offsets: {payload['start_offset']}-{payload['end_offset']}",
        f"- Governed batches: {payload['batch_count']}",
        f"- Listing rows evaluated: {payload['listing_rows']}",
        f"- Accepted listings: {payload['accepted_rows']}",
        f"- Manual-review listings: {payload['review_rows']}",
        f"- Rejected listings: {payload['rejected_rows']}",
        f"- Source errors: {payload['source_errors']}",
        f"- Accepted exceptions: {payload['accepted_exception_rows']}",
        f"- Cross-product duplicate rows: {payload['cross_product_duplicate_rows']}",
        "",
        "## Lane Checks",
        "",
    ]
    for name, value in payload["checks"].items():
        lines.append(f"- {name}: {'PASS' if value else 'FAIL'}")
    lines.extend(["", "## Batch Results", "", "| Batch | Products | Listings | Accepted | Review | Rejected | Status |", "|---|---:|---:|---:|---:|---:|---|"])
    for batch in payload["batches"]:
        lines.append(
            f"| {batch['batch_key']} | {batch['products']} | {batch['listing_rows']} | "
            f"{batch['accepted_rows']} | {batch['review_rows']} | {batch['rejected_rows']} | {batch['status']} |"
        )
    lines.extend([
        "",
        "## Certification Decision",
        "",
        "The complete 973-product operational English Secret Lair eBay matching universe is certified only when every lane and batch check passes. Generated batch evidence remains outside source control.",
        "",
    ])
    return "\n".join(lines)


def certify_lane(batches_root: Path, output_root: Path, low_score_threshold: float = 0.82) -> dict[str, Any]:
    discovered = discover_batches(batches_root)
    batch_results = [certify_batch(start, end, path, low_score_threshold) for start, end, path in discovered]
    ranges = [(result["start_offset"], result["end_offset"]) for result in batch_results]

    totals = {
        key: sum(int(batch[key]) for batch in batch_results)
        for key in (
            "products", "listing_rows", "accepted_rows", "review_rows", "rejected_rows",
            "source_errors", "accepted_exception_rows", "cross_product_duplicate_rows",
        )
    }
    all_ids: set[str] = set()
    for batch in batch_results:
        for row in read_csv(Path(batch["coverage_path"])):
            product_id = (row.get("canonical_product_id") or "").strip()
            if product_id:
                all_ids.add(product_id)

    checks = {
        "batches_discovered": bool(batch_results),
        "starts_at_zero": bool(ranges) and ranges[0][0] == EXPECTED_START,
        "ends_at_972": bool(ranges) and ranges[-1][1] == EXPECTED_END,
        "ranges_contiguous": contiguous_ranges(ranges),
        "products_total_973": totals["products"] == EXPECTED_PRODUCTS,
        "unique_products_total_973": len(all_ids) == EXPECTED_PRODUCTS,
        "source_errors_zero": totals["source_errors"] == 0,
        "accepted_exceptions_zero": totals["accepted_exception_rows"] == 0,
        "cross_product_duplicates_zero": totals["cross_product_duplicate_rows"] == 0,
        "all_batches_certified": all(batch["status"] == "CERTIFIED" for batch in batch_results),
    }

    payload: dict[str, Any] = {
        "status": "CERTIFIED" if all(checks.values()) else "FAILED",
        "certified_at_utc": datetime.now(timezone.utc).isoformat(),
        "batches_root": str(batches_root.resolve()),
        "output_root": str(output_root.resolve()),
        "start_offset": ranges[0][0] if ranges else None,
        "end_offset": ranges[-1][1] if ranges else None,
        "batch_count": len(batch_results),
        "unique_product_ids": len(all_ids),
        **totals,
        "checks": checks,
        "batches": batch_results,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "secret_lair_ebay_lane_certification.json"
    markdown_path = output_root / "SECRET_LAIR_EBAY_LANE_CERTIFICATION.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(build_markdown(payload), encoding="utf-8")
    payload["outputs"] = {
        "json": str(json_path.resolve()),
        "markdown": str(markdown_path.resolve()),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches-root", type=Path, default=DEFAULT_BATCHES_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--low-score-threshold", type=float, default=0.82)
    args = parser.parse_args()
    payload = certify_lane(args.batches_root, args.output_root, args.low_score_threshold)
    print("SECRET LAIR EBAY LANE CERTIFICATION: COMPLETE")
    print(json.dumps(payload, indent=2))
    if payload["status"] != "CERTIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
'''

TEST_CONTENT = r'''from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "certify_secret_lair_ebay_lane",
    ROOT / "scripts/certify_secret_lair_ebay_lane.py",
)
assert SPEC and SPEC.loader
CERT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CERT)


def test_parse_batch_range():
    assert CERT.parse_batch_range(Path("sealed_secret_lair_0830_0972")) == (830, 972)


def test_contiguous_ranges():
    assert CERT.contiguous_ranges([(0, 229), (230, 429), (430, 629), (630, 829), (830, 972)])
    assert not CERT.contiguous_ranges([(0, 229), (231, 429)])


def test_build_markdown_contains_certification_scope():
    payload = {
        "status": "CERTIFIED",
        "certified_at_utc": "2026-07-24T00:00:00+00:00",
        "products": 973,
        "start_offset": 0,
        "end_offset": 972,
        "batch_count": 5,
        "listing_rows": 100,
        "accepted_rows": 25,
        "review_rows": 25,
        "rejected_rows": 50,
        "source_errors": 0,
        "accepted_exception_rows": 0,
        "cross_product_duplicate_rows": 0,
        "checks": {"products_total_973": True},
        "batches": [{
            "batch_key": "sealed_secret_lair_0000_0229",
            "products": 230,
            "listing_rows": 10,
            "accepted_rows": 2,
            "review_rows": 3,
            "rejected_rows": 5,
            "status": "CERTIFIED",
        }],
    }
    markdown = CERT.build_markdown(payload)
    assert "973" in markdown
    assert "sealed_secret_lair_0000_0229" in markdown
    assert "products_total_973: PASS" in markdown


def test_cross_product_duplicate_count():
    rows = [
        {"match_state": "ACCEPTED", "ebay_item_id": "1", "canonical_product_id": "A"},
        {"match_state": "ACCEPTED", "ebay_item_id": "1", "canonical_product_id": "B"},
        {"match_state": "REJECTED", "ebay_item_id": "1", "canonical_product_id": "C"},
    ]
    assert CERT.cross_product_duplicate_count(rows) == 2
'''


def apply() -> None:
    if CERTIFIER.exists() or TESTS.exists():
        raise RuntimeError("Lane certification source already exists; refusing to overwrite")
    CERTIFIER.write_text(CERTIFIER_CONTENT, encoding="utf-8")
    TESTS.write_text(TEST_CONTENT, encoding="utf-8")
    print("SECRET LAIR EBAY LANE CERTIFICATION: APPLIED")
    print(f"Created: {CERTIFIER.relative_to(ROOT)}")
    print(f"Created: {TESTS.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
