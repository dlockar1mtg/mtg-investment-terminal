import csv
import json
from pathlib import Path

from scripts.promote_ebay_consolidation import certify


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_package(root: Path, *, audit_status: str = "PASS", source_error: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    ids = ["A", "B"]
    coverage = [
        {"canonical_product_id": value, "coverage_state": "SOURCE_ERROR" if source_error and value == "B" else "NO_MATCHES"}
        for value in ids
    ]
    listings = [
        {"canonical_product_id": "A", "ebay_item_id": "1", "match_state": "ACCEPTED"},
        {"canonical_product_id": "B", "ebay_item_id": "2", "match_state": "REVIEW"},
    ]
    write_csv(root / "ebay_product_coverage_2026-07-24.csv", ["canonical_product_id", "coverage_state"], coverage)
    write_csv(root / "ebay_canonical_match_universe_2026-07-24.csv", ["canonical_product_id"], [{"canonical_product_id": value} for value in ids])
    write_csv(root / "ebay_listing_match_results_2026-07-24.csv", ["canonical_product_id", "ebay_item_id", "match_state"], listings)
    write_csv(root / "ebay_manual_review_2026-07-24.csv", ["canonical_product_id", "ebay_item_id", "match_state"], [listings[1]])
    (root / "consolidation_manifest.json").write_text(json.dumps({
        "status": "PENDING_CERTIFICATION",
        "expected_products": 2,
        "products": 2,
        "unique_product_ids": 2,
        "source_errors": 1 if source_error else 0,
        "attempt_audit_status": "PASS",
    }), encoding="utf-8")
    audit_root = root / "exception_audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    (audit_root / "audit_report.json").write_text(json.dumps({
        "status": audit_status,
        "accepted_exception_rows": 0,
        "cross_product_duplicate_rows": 0,
    }), encoding="utf-8")


def test_certify_accepts_complete_clean_package(tmp_path):
    root = tmp_path / "consolidated"
    build_package(root)
    result = certify(root, 2)
    assert result["products"] == 2
    assert result["source_errors"] == 0
    assert all(result["checks"].values())


def test_certify_rejects_failed_audit(tmp_path):
    root = tmp_path / "consolidated"
    build_package(root, audit_status="REVIEW_REQUIRED")
    try:
        certify(root, 2)
    except RuntimeError as exc:
        assert "audit_pass" in str(exc)
    else:
        raise AssertionError("Expected certification failure")


def test_certify_rejects_source_error(tmp_path):
    root = tmp_path / "consolidated"
    build_package(root, source_error=True)
    try:
        certify(root, 2)
    except RuntimeError as exc:
        assert "source_errors" in str(exc)
    else:
        raise AssertionError("Expected certification failure")
