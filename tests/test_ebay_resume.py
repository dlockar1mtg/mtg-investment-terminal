import csv
from pathlib import Path

from terminal2.market_sources.ebay_resume import build_resume_plan


def write_coverage(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_product_id", "coverage_state"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_resume_plan_marks_non_source_error_products_complete(tmp_path):
    batch_root = tmp_path / "batch"
    write_coverage(
        batch_root / "attempts/attempt_20260723T010000Z/ebay_product_coverage_RUN1.csv",
        [
            {"canonical_product_id": "A", "coverage_state": "STRONG"},
            {"canonical_product_id": "B", "coverage_state": "SOURCE_ERROR"},
        ],
    )
    plan = build_resume_plan(batch_root, ["A", "B", "C"])
    assert plan.completed_product_ids == ("A",)
    assert plan.pending_product_ids == ("B", "C")
    assert plan.source_error_product_ids == ("B",)


def test_latest_attempt_can_replace_prior_source_error(tmp_path):
    batch_root = tmp_path / "batch"
    write_coverage(
        batch_root / "attempts/attempt_20260723T010000Z/ebay_product_coverage_RUN1.csv",
        [{"canonical_product_id": "A", "coverage_state": "SOURCE_ERROR"}],
    )
    write_coverage(
        batch_root / "attempts/attempt_20260723T020000Z/ebay_product_coverage_RUN2.csv",
        [{"canonical_product_id": "A", "coverage_state": "LIMITED"}],
    )
    plan = build_resume_plan(batch_root, ["A"])
    assert plan.completed_product_ids == ("A",)
    assert plan.pending_product_ids == ()
    assert plan.is_complete


def test_no_attempts_leaves_all_products_pending(tmp_path):
    plan = build_resume_plan(tmp_path / "batch", ["A", "B"])
    assert plan.completed_product_ids == ()
    assert plan.pending_product_ids == ("A", "B")
    assert plan.coverage_files == ()


def test_legacy_batch_root_coverage_is_discovered(tmp_path):
    batch_root = tmp_path / "batch"
    write_coverage(
        batch_root / "ebay_product_coverage_2026-07-23.csv",
        [
            {"canonical_product_id": "A", "coverage_state": "STRONG"},
            {"canonical_product_id": "B", "coverage_state": "SOURCE_ERROR"},
        ],
    )
    plan = build_resume_plan(batch_root, ["A", "B", "C"])
    assert plan.completed_product_ids == ("A",)
    assert plan.pending_product_ids == ("B", "C")
    assert plan.source_error_product_ids == ("B",)
    assert len(plan.coverage_files) == 1


def test_new_attempt_supersedes_legacy_batch_root_state(tmp_path):
    batch_root = tmp_path / "batch"
    write_coverage(
        batch_root / "ebay_product_coverage_2026-07-23.csv",
        [{"canonical_product_id": "A", "coverage_state": "SOURCE_ERROR"}],
    )
    write_coverage(
        batch_root / "attempts/attempt_20260724T080000Z/ebay_product_coverage_2026-07-24.csv",
        [{"canonical_product_id": "A", "coverage_state": "LIMITED"}],
    )
    plan = build_resume_plan(batch_root, ["A"])
    assert plan.completed_product_ids == ("A",)
    assert plan.pending_product_ids == ()
    assert len(plan.coverage_files) == 2

