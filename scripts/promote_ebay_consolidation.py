from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


DATA_PATTERNS = (
    "ebay_canonical_match_universe_*.csv",
    "ebay_listing_match_results_*.csv",
    "ebay_manual_review_*.csv",
    "ebay_product_coverage_*.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Certify and atomically promote a governed eBay consolidation package."
    )
    parser.add_argument("--batch-root", required=True)
    parser.add_argument("--consolidated-root", required=True)
    parser.add_argument("--expected-products", type=int, required=True)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def latest_file(root: Path, pattern: str) -> Path:
    files = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No file matching {pattern!r} under {root}")
    return files[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def certify(consolidated_root: Path, expected_products: int) -> dict[str, Any]:
    manifest_path = consolidated_root / "consolidation_manifest.json"
    audit_path = consolidated_root / "exception_audit" / "audit_report.json"
    manifest = read_json(manifest_path)
    audit = read_json(audit_path)

    coverage_path = latest_file(consolidated_root, "ebay_product_coverage_*.csv")
    listings_path = latest_file(consolidated_root, "ebay_listing_match_results_*.csv")
    universe_path = latest_file(consolidated_root, "ebay_canonical_match_universe_*.csv")
    manual_path = latest_file(consolidated_root, "ebay_manual_review_*.csv")

    coverage = read_csv(coverage_path)
    listings = read_csv(listings_path)
    universe = read_csv(universe_path)
    manual = read_csv(manual_path)

    product_ids = [row.get("canonical_product_id", "").strip() for row in coverage]
    source_errors = [row for row in coverage if row.get("coverage_state", "").strip().upper() == "SOURCE_ERROR"]
    duplicate_product_ids = len(product_ids) - len(set(product_ids))

    accepted = [row for row in listings if row.get("match_state", "").strip().upper() == "ACCEPTED"]
    review = [row for row in listings if row.get("match_state", "").strip().upper() == "REVIEW"]
    rejected = [row for row in listings if row.get("match_state", "").strip().upper() == "REJECTED"]

    checks = {
        "manifest_pending_certification": manifest.get("status") == "PENDING_CERTIFICATION",
        "manifest_expected_products": int(manifest.get("expected_products", -1)) == expected_products,
        "manifest_products": int(manifest.get("products", -1)) == expected_products,
        "manifest_unique_products": int(manifest.get("unique_product_ids", -1)) == expected_products,
        "manifest_source_errors_zero": int(manifest.get("source_errors", -1)) == 0,
        "manifest_attempt_audit_pass": manifest.get("attempt_audit_status") == "PASS",
        "audit_pass": audit.get("status") == "PASS",
        "audit_accepted_exceptions_zero": int(audit.get("accepted_exception_rows", -1)) == 0,
        "audit_cross_product_duplicates_zero": int(audit.get("cross_product_duplicate_rows", -1)) == 0,
        "coverage_rows": len(coverage) == expected_products,
        "coverage_unique_products": len(set(product_ids)) == expected_products,
        "coverage_blank_products_zero": all(product_ids),
        "coverage_duplicate_products_zero": duplicate_product_ids == 0,
        "coverage_source_errors_zero": len(source_errors) == 0,
        "universe_rows": len(universe) == expected_products,
        "manual_review_consistent": len(manual) == len(review),
        "listing_state_partition": len(listings) == len(accepted) + len(review) + len(rejected),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Consolidation certification failed: " + ", ".join(failed))

    files = [universe_path, listings_path, manual_path, coverage_path, manifest_path, audit_path]
    return {
        "checks": checks,
        "products": len(coverage),
        "unique_product_ids": len(set(product_ids)),
        "source_errors": len(source_errors),
        "listing_rows": len(listings),
        "accepted_rows": len(accepted),
        "review_rows": len(review),
        "rejected_rows": len(rejected),
        "files": {
            path.name if path.parent == consolidated_root else f"exception_audit/{path.name}": {
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        },
    }


def promote(batch_root: Path, consolidated_root: Path, expected_products: int) -> dict[str, Any]:
    certification = certify(consolidated_root, expected_products)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = batch_root / "promotion_backups" / f"backup_{timestamp}"
    staging_root = batch_root / ".promotion_staging" / f"staging_{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    staging_root.mkdir(parents=True, exist_ok=False)

    source_files: list[Path] = []
    for pattern in DATA_PATTERNS:
        source_files.append(latest_file(consolidated_root, pattern))

    for source in source_files:
        shutil.copy2(source, staging_root / source.name)

    for pattern in DATA_PATTERNS:
        for existing in batch_root.glob(pattern):
            if existing.is_file():
                shutil.copy2(existing, backup_root / existing.name)

    existing_manifest = batch_root / "batch_manifest.json"
    if existing_manifest.exists():
        shutil.copy2(existing_manifest, backup_root / existing_manifest.name)

    for pattern in DATA_PATTERNS:
        for existing in batch_root.glob(pattern):
            if existing.is_file():
                existing.unlink()

    for staged in staging_root.iterdir():
        if staged.is_file():
            staged.replace(batch_root / staged.name)

    promoted_at = datetime.now(timezone.utc).isoformat()
    promotion_manifest = {
        "status": "CERTIFIED",
        "promoted_at_utc": promoted_at,
        "batch_root": str(batch_root.resolve()),
        "consolidated_root": str(consolidated_root.resolve()),
        "backup_root": str(backup_root.resolve()),
        "expected_products": expected_products,
        **certification,
    }
    (batch_root / "certified_consolidation_manifest.json").write_text(
        json.dumps(promotion_manifest, indent=2), encoding="utf-8"
    )

    batch_manifest = {
        "status": "CERTIFIED",
        "certification_type": "RESUME_CONSOLIDATION",
        "promoted_at_utc": promoted_at,
        "expected_products": expected_products,
        "products": certification["products"],
        "unique_product_ids": certification["unique_product_ids"],
        "source_errors": certification["source_errors"],
        "listing_rows": certification["listing_rows"],
        "accepted_rows": certification["accepted_rows"],
        "review_rows": certification["review_rows"],
        "rejected_rows": certification["rejected_rows"],
        "consolidated_root": str(consolidated_root.resolve()),
        "certification_manifest": str((batch_root / "certified_consolidation_manifest.json").resolve()),
    }
    (batch_root / "batch_manifest.json").write_text(
        json.dumps(batch_manifest, indent=2), encoding="utf-8"
    )

    try:
        staging_root.rmdir()
        staging_root.parent.rmdir()
    except OSError:
        pass

    return promotion_manifest


def main() -> int:
    args = parse_args()
    batch_root = Path(args.batch_root).resolve()
    consolidated_root = Path(args.consolidated_root).resolve()
    if args.expected_products < 1:
        raise SystemExit("--expected-products must be at least 1")
    if not batch_root.exists():
        raise FileNotFoundError(batch_root)
    if not consolidated_root.exists():
        raise FileNotFoundError(consolidated_root)

    result = promote(batch_root, consolidated_root, args.expected_products)
    print("EBAY CERTIFIED CONSOLIDATION PROMOTION: COMPLETE")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
