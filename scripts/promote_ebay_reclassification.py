from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

PRIMARY_PATTERNS = (
    "ebay_canonical_match_universe_*.csv",
    "ebay_listing_match_results_*.csv",
    "ebay_manual_review_*.csv",
    "ebay_product_coverage_*.csv",
    "ebay_matching_summary_*.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def one(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {pattern} in {root}; found {len(matches)}")
    return matches[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def promote(batch_root: Path, candidate_root: Path) -> dict[str, object]:
    batch_root = batch_root.resolve()
    candidate_root = candidate_root.resolve()
    manifest_path = candidate_root / "reclassification_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PENDING_AUDIT":
        raise RuntimeError("Candidate manifest must be PENDING_AUDIT")
    if int(manifest.get("quota_calls", -1)) != 0:
        raise RuntimeError("Candidate must record quota_calls=0")

    listings = read_csv(one(candidate_root, "ebay_listing_match_results_*.csv"))
    coverage = read_csv(one(candidate_root, "ebay_product_coverage_*.csv"))
    accepted = [r for r in listings if r.get("match_state") == "ACCEPTED"]
    duplicate_pairs = len(listings) - len({(r.get("canonical_product_id"), r.get("ebay_item_id")) for r in listings})
    cross_duplicates = len(accepted) - len({r.get("ebay_item_id") for r in accepted})
    exceptions_path = candidate_root / "exception_audit" / "accepted_exceptions.csv"
    exceptions = read_csv(exceptions_path) if exceptions_path.exists() else []

    checks = {
        "products_match": len(coverage) == int(manifest["products"]),
        "unique_products_match": len({r.get("canonical_product_id") for r in coverage}) == int(manifest["unique_product_ids"]),
        "source_errors_zero": not any(r.get("coverage_state") == "SOURCE_ERROR" for r in coverage),
        "listing_rows_match": len(listings) == int(manifest["listing_rows"]),
        "duplicate_product_items_zero": duplicate_pairs == 0,
        "accepted_exceptions_zero": len(exceptions) == 0,
        "cross_product_duplicates_zero": cross_duplicates == 0,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Promotion checks failed: {checks}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = batch_root / "promotion_backups" / f"backup_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)

    promoted: dict[str, dict[str, object]] = {}
    for pattern in PRIMARY_PATTERNS:
        source = one(candidate_root, pattern)
        destination = batch_root / source.name
        if destination.exists():
            shutil.copy2(destination, backup_root / destination.name)
        shutil.copy2(source, destination)
        if sha256(source) != sha256(destination):
            raise RuntimeError(f"Hash mismatch after promoting {source.name}")
        promoted[source.name] = {"sha256": sha256(destination), "bytes": destination.stat().st_size}

    source_audit = candidate_root / "exception_audit"
    destination_audit = batch_root / "exception_audit"
    if destination_audit.exists():
        shutil.copytree(destination_audit, backup_root / "exception_audit")
        shutil.rmtree(destination_audit)
    shutil.copytree(source_audit, destination_audit)

    summary = json.loads(one(batch_root, "ebay_matching_summary_*.json").read_text(encoding="utf-8"))
    promotion = {
        "status": "CERTIFIED",
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_root": str(batch_root),
        "candidate_root": str(candidate_root),
        "backup_root": str(backup_root),
        "checks": checks,
        "products": len(coverage),
        "listing_rows": len(listings),
        "accepted_rows": sum(r.get("match_state") == "ACCEPTED" for r in listings),
        "review_rows": sum(r.get("match_state") == "REVIEW" for r in listings),
        "rejected_rows": sum(r.get("match_state") == "REJECTED" for r in listings),
        "source_errors": sum(r.get("coverage_state") == "SOURCE_ERROR" for r in coverage),
        "quota_calls": 0,
        "summary_aborted_early": bool(summary.get("aborted_early")),
        "promoted_files": promoted,
    }
    (batch_root / "reclassification_promotion_manifest.json").write_text(
        json.dumps(promotion, indent=2), encoding="utf-8"
    )
    return promotion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    args = parser.parse_args()
    result = promote(Path(args.batch_root), Path(args.candidate_root))
    print("EBAY RECLASSIFICATION PROMOTION: COMPLETE")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
