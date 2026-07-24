from __future__ import annotations

import importlib.util
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
    assert CERT.contiguous_ranges([(0, 4), (5, 9), (10, 14)])
    assert not CERT.contiguous_ranges([(0, 4), (6, 9)])


def test_select_governed_partition_excludes_overlap(tmp_path):
    names = [
        "sealed_secret_lair_0000_0004",
        "sealed_secret_lair_0000_0024",
        "sealed_secret_lair_0005_0009",
        "sealed_secret_lair_0010_0014",
        "sealed_secret_lair_0015_0019",
        "sealed_secret_lair_0020_0029",
        "sealed_secret_lair_0030_0972",
    ]
    discovered = []
    for name in names:
        path = tmp_path / name
        path.mkdir()
        start, end = CERT.parse_batch_range(path)
        discovered.append((start, end, path))
    selected = CERT.select_governed_partition(discovered, start=0, end=972)
    assert [path.name for _, _, path in selected] == [
        "sealed_secret_lair_0000_0004",
        "sealed_secret_lair_0005_0009",
        "sealed_secret_lair_0010_0014",
        "sealed_secret_lair_0015_0019",
        "sealed_secret_lair_0020_0029",
        "sealed_secret_lair_0030_0972",
    ]


def test_cross_product_duplicate_count():
    rows = [
        {"match_state": "ACCEPTED", "ebay_item_id": "1", "canonical_product_id": "A"},
        {"match_state": "ACCEPTED", "ebay_item_id": "1", "canonical_product_id": "B"},
        {"match_state": "REJECTED", "ebay_item_id": "1", "canonical_product_id": "C"},
    ]
    assert CERT.cross_product_duplicate_count(rows) == 2


def test_build_markdown_reports_excluded_batches():
    payload = {
        "status": "CERTIFIED",
        "certified_at_utc": "2026-07-24T00:00:00+00:00",
        "products": 973,
        "start_offset": 0,
        "end_offset": 972,
        "batch_count": 14,
        "excluded_batch_count": 1,
        "excluded_batches": ["sealed_secret_lair_0000_0024"],
        "listing_rows": 100,
        "accepted_rows": 25,
        "review_rows": 25,
        "rejected_rows": 50,
        "source_errors": 0,
        "accepted_exception_rows": 0,
        "cross_product_duplicate_rows": 0,
        "checks": {"products_total_973": True},
        "batches": [{
            "batch_key": "sealed_secret_lair_0000_0004",
            "products": 5,
            "listing_rows": 10,
            "accepted_rows": 2,
            "review_rows": 3,
            "rejected_rows": 5,
            "summary_mode": "LEGACY_CSV_EVIDENCE",
            "status": "CERTIFIED",
        }],
    }
    markdown = CERT.build_markdown(payload)
    assert "sealed_secret_lair_0000_0024" in markdown
    assert "LEGACY_CSV_EVIDENCE" in markdown
