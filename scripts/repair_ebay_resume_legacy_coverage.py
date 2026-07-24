from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESUME_PATH = ROOT / "terminal2/market_sources/ebay_resume.py"
TEST_PATH = ROOT / "tests/test_ebay_resume.py"

OLD = '''def _coverage_files(batch_root: Path) -> list[Path]:
    attempts_root = batch_root / "attempts"
    if not attempts_root.exists():
        return []
    return sorted(
        attempts_root.glob("attempt_*/ebay_product_coverage_*.csv"),
        key=lambda path: (path.parent.name, path.name),
    )
'''

NEW = '''def _coverage_files(batch_root: Path) -> list[Path]:
    # Legacy batches wrote their latest coverage CSV directly into the batch root.
    # New protected runs write one coverage CSV beneath each timestamped attempt.
    # Process legacy files first and attempts in chronological path order so later
    # attempt states supersede the older batch-root snapshot.
    legacy_files = sorted(batch_root.glob("ebay_product_coverage_*.csv"))
    attempt_files = sorted(
        (batch_root / "attempts").glob("attempt_*/ebay_product_coverage_*.csv"),
        key=lambda path: (path.parent.name, path.name),
    )
    return legacy_files + attempt_files
'''

TEST_APPEND = '''


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
'''


def apply() -> None:
    resume = RESUME_PATH.read_text(encoding="utf-8")
    if "legacy_files = sorted" not in resume:
        if OLD not in resume:
            raise RuntimeError("Expected resume coverage discovery block was not found")
        resume = resume.replace(OLD, NEW, 1)
        RESUME_PATH.write_text(resume, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    if "test_legacy_batch_root_coverage_is_discovered" not in tests:
        tests = tests.rstrip() + TEST_APPEND + "\n"
        TEST_PATH.write_text(tests, encoding="utf-8")

    print("EBAY RESUME LEGACY COVERAGE REPAIR: APPLIED")
    print(f"Updated: {RESUME_PATH.relative_to(ROOT)}")
    print(f"Updated: {TEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
