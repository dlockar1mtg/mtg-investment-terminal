from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def only_file(root: Path, pattern: str) -> Path:
    files = sorted(root.glob(pattern))
    if len(files) != 1:
        raise RuntimeError(f"Expected exactly one {pattern!r} under {root}; found {len(files)}")
    return files[0]


def latest_attempt(batch_root: Path) -> Path:
    attempts = sorted(
        (path for path in (batch_root / "attempts").glob("attempt_*") if path.is_dir()),
        key=lambda path: path.name,
    )
    if not attempts:
        raise RuntimeError(f"No resume attempts found under {batch_root}")
    return attempts[-1]


def merge_rows_by_product(
    expected_ids: list[str],
    legacy_rows: list[dict[str, str]],
    attempt_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    expected = set(expected_ids)
    latest: dict[str, dict[str, str]] = {}
    source: dict[str, str] = {}
    for label, rows in (("legacy", legacy_rows), ("attempt", attempt_rows)):
        for row in rows:
            product_id = str(row.get("canonical_product_id", "")).strip()
            if product_id in expected:
                latest[product_id] = row
                source[product_id] = label
    missing = [product_id for product_id in expected_ids if product_id not in latest]
    if missing:
        raise RuntimeError(f"Missing consolidated product rows: {missing[:10]}")
    merged = [latest[product_id] for product_id in expected_ids]
    return merged, source


def select_listing_rows(
    rows: list[dict[str, str]],
    source_map: dict[str, str],
    source_label: str,
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if source_map.get(str(row.get("canonical_product_id", "")).strip()) == source_label
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate a legacy eBay batch with its latest clean resume attempt.")
    parser.add_argument("--batch-root", required=True)
    parser.add_argument("--attempt-root")
    parser.add_argument("--expected-products", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    batch_root = Path(args.batch_root).resolve()
    attempt_root = Path(args.attempt_root).resolve() if args.attempt_root else latest_attempt(batch_root)
    if not batch_root.exists() or not attempt_root.exists():
        raise FileNotFoundError(batch_root if not batch_root.exists() else attempt_root)

    audit_path = attempt_root / "exception_audit/audit_report.json"
    if not audit_path.exists():
        raise RuntimeError("Resume attempt has not been exception-audited")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS":
        raise RuntimeError(f"Resume attempt audit is not PASS: {audit.get('status')}")

    legacy_universe_path = only_file(batch_root, "ebay_canonical_match_universe_*.csv")
    legacy_coverage_path = only_file(batch_root, "ebay_product_coverage_*.csv")
    legacy_listing_path = only_file(batch_root, "ebay_listing_match_results_*.csv")
    attempt_universe_path = only_file(attempt_root, "ebay_canonical_match_universe_*.csv")
    attempt_coverage_path = only_file(attempt_root, "ebay_product_coverage_*.csv")
    attempt_listing_path = only_file(attempt_root, "ebay_listing_match_results_*.csv")

    legacy_universe = read_csv(legacy_universe_path)
    attempt_universe = read_csv(attempt_universe_path)
    expected_ids = [str(row.get("canonical_product_id", "")).strip() for row in legacy_universe]
    expected_ids = [value for value in expected_ids if value]
    if len(expected_ids) != args.expected_products or len(set(expected_ids)) != args.expected_products:
        raise RuntimeError(
            f"Legacy universe mismatch: expected={args.expected_products} rows={len(expected_ids)} unique={len(set(expected_ids))}"
        )

    merged_universe, universe_source = merge_rows_by_product(expected_ids, legacy_universe, attempt_universe)
    merged_coverage, coverage_source = merge_rows_by_product(
        expected_ids,
        read_csv(legacy_coverage_path),
        read_csv(attempt_coverage_path),
    )
    if universe_source != coverage_source:
        raise RuntimeError("Universe and coverage source selection disagree")

    source_errors = [row for row in merged_coverage if str(row.get("coverage_state", "")).upper() == "SOURCE_ERROR"]
    if source_errors:
        raise RuntimeError(f"Consolidated coverage still contains {len(source_errors)} SOURCE_ERROR rows")

    legacy_listings = select_listing_rows(read_csv(legacy_listing_path), coverage_source, "legacy")
    attempt_listings = select_listing_rows(read_csv(attempt_listing_path), coverage_source, "attempt")
    merged_listings = legacy_listings + attempt_listings

    duplicate_keys = Counter(
        (str(row.get("canonical_product_id", "")).strip(), str(row.get("ebay_item_id", "")).strip())
        for row in merged_listings
        if str(row.get("ebay_item_id", "")).strip()
    )
    exact_duplicates = [key for key, count in duplicate_keys.items() if count > 1]
    if exact_duplicates:
        raise RuntimeError(f"Consolidated listings contain duplicate product/item pairs: {exact_duplicates[:10]}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = batch_root / "consolidated" / f"consolidation_{timestamp}"
    if output_root.exists() and not args.force:
        raise RuntimeError(f"Output already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    date = datetime.now(timezone.utc).date().isoformat()
    write_csv(output_root / f"ebay_canonical_match_universe_{date}.csv", merged_universe, merged_universe[0].keys())
    write_csv(output_root / f"ebay_product_coverage_{date}.csv", merged_coverage, merged_coverage[0].keys())
    write_csv(output_root / f"ebay_listing_match_results_{date}.csv", merged_listings, merged_listings[0].keys())
    manual = [row for row in merged_listings if str(row.get("match_state", "")).upper() == "REVIEW"]
    write_csv(
        output_root / f"ebay_manual_review_{date}.csv",
        manual,
        merged_listings[0].keys(),
    )

    state_counts = Counter(str(row.get("match_state", "")).upper() for row in merged_listings)
    coverage_counts = Counter(str(row.get("coverage_state", "")).upper() for row in merged_coverage)
    manifest = {
        "status": "PENDING_CERTIFICATION",
        "consolidated_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_root": str(batch_root),
        "legacy_source": str(batch_root),
        "attempt_source": str(attempt_root),
        "expected_products": args.expected_products,
        "products": len(merged_coverage),
        "unique_product_ids": len({row["canonical_product_id"] for row in merged_coverage}),
        "legacy_products_reused": sum(value == "legacy" for value in coverage_source.values()),
        "attempt_products_used": sum(value == "attempt" for value in coverage_source.values()),
        "source_errors": len(source_errors),
        "listing_rows": len(merged_listings),
        "accepted_rows": state_counts.get("ACCEPTED", 0),
        "review_rows": state_counts.get("REVIEW", 0),
        "rejected_rows": state_counts.get("REJECTED", 0),
        "coverage_states": dict(sorted(coverage_counts.items())),
        "attempt_audit_status": audit.get("status"),
        "output_root": str(output_root),
    }
    (output_root / "consolidation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("EBAY GOVERNED RESUME CONSOLIDATION: COMPLETE")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
