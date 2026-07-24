from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESUME_PATH = ROOT / "terminal2/market_sources/ebay_resume.py"
RUNNER_PATH = ROOT / "scripts/run_ebay_matching_batch.py"
TEST_PATH = ROOT / "tests/test_ebay_resume.py"

RESUME_CONTENT = '''from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ResumePlan:
    expected_product_ids: tuple[str, ...]
    completed_product_ids: tuple[str, ...]
    pending_product_ids: tuple[str, ...]
    source_error_product_ids: tuple[str, ...]
    coverage_files: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.pending_product_ids


def _coverage_files(batch_root: Path) -> list[Path]:
    attempts_root = batch_root / "attempts"
    if not attempts_root.exists():
        return []
    return sorted(
        attempts_root.glob("attempt_*/ebay_product_coverage_*.csv"),
        key=lambda path: (path.parent.name, path.name),
    )


def build_resume_plan(batch_root: Path, expected_product_ids: Sequence[str]) -> ResumePlan:
    expected = tuple(dict.fromkeys(str(value) for value in expected_product_ids))
    expected_set = set(expected)
    latest_state: dict[str, str] = {}
    files = _coverage_files(batch_root)

    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                product_id = str(row.get("canonical_product_id", "")).strip()
                if not product_id or product_id not in expected_set:
                    continue
                state = str(row.get("coverage_state", "")).strip().upper()
                latest_state[product_id] = state

    completed = tuple(
        product_id
        for product_id in expected
        if latest_state.get(product_id) and latest_state[product_id] != "SOURCE_ERROR"
    )
    source_errors = tuple(
        product_id
        for product_id in expected
        if latest_state.get(product_id) == "SOURCE_ERROR"
    )
    pending = tuple(product_id for product_id in expected if product_id not in set(completed))

    return ResumePlan(
        expected_product_ids=expected,
        completed_product_ids=completed,
        pending_product_ids=pending,
        source_error_product_ids=source_errors,
        coverage_files=tuple(str(path) for path in files),
    )


def select_pending_products(products: Iterable[object], pending_ids: Sequence[str]) -> list[object]:
    pending = set(pending_ids)
    return [
        product
        for product in products
        if str(getattr(product, "canonical_product_id")) in pending
    ]
'''

TEST_CONTENT = '''import csv
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
'''

IMPORT_OLD = '''from terminal2.market_sources.ebay_resilience import (
    estimate_batch_calls,
    format_reset_local,
    get_browse_quota,
)
from terminal2.market_sources.ebay_universe import build_complete_universe
'''

IMPORT_NEW = '''from terminal2.market_sources.ebay_resilience import (
    estimate_batch_calls,
    format_reset_local,
    get_browse_quota,
)
from terminal2.market_sources.ebay_resume import build_resume_plan, select_pending_products
from terminal2.market_sources.ebay_universe import build_complete_universe
'''

ARG_OLD = '''    parser.add_argument("--quota-reserve", type=int, default=100)
    args = parser.parse_args()
'''

ARG_NEW = '''    parser.add_argument("--quota-reserve", type=int, default=100)
    parser.add_argument(
        "--resume-plan",
        action="store_true",
        help="Inspect prior attempts and report which selected products remain unfinished.",
    )
    args = parser.parse_args()
'''

ROOT_OLD = '''    end = args.offset + len(subset) - 1
    batch_key = f"{args.product_class.lower()}_{args.offset:04d}_{end:04d}"
    batch_root = base.OUTPUT_ROOT / "batches" / batch_key
    attempt_key = datetime.now(timezone.utc).strftime("attempt_%Y%m%dT%H%M%SZ")
'''

ROOT_NEW = '''    end = args.offset + len(subset) - 1
    batch_key = f"{args.product_class.lower()}_{args.offset:04d}_{end:04d}"
    batch_root = base.OUTPUT_ROOT / "batches" / batch_key

    if args.resume_plan:
        plan = build_resume_plan(
            batch_root,
            [product.canonical_product_id for product in subset],
        )
        print("EBAY BATCH RESUME PLAN")
        print(f"  batch: {batch_key}")
        print(f"  expected products: {len(plan.expected_product_ids)}")
        print(f"  completed products: {len(plan.completed_product_ids)}")
        print(f"  pending products: {len(plan.pending_product_ids)}")
        print(f"  prior source errors: {len(plan.source_error_product_ids)}")
        print(f"  coverage files inspected: {len(plan.coverage_files)}")
        print(f"  estimated maximum resume calls: {estimate_batch_calls(len(plan.pending_product_ids))}")
        if plan.pending_product_ids:
            print("  pending product IDs:")
            for product_id in plan.pending_product_ids:
                print(f"    {product_id}")
        return 0

    attempt_key = datetime.now(timezone.utc).strftime("attempt_%Y%m%dT%H%M%SZ")
'''


def apply() -> None:
    RESUME_PATH.write_text(RESUME_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    if "from terminal2.market_sources.ebay_resume import" not in runner:
        if IMPORT_OLD not in runner:
            raise RuntimeError("Expected resilience import block not found")
        runner = runner.replace(IMPORT_OLD, IMPORT_NEW, 1)
    if '"--resume-plan"' not in runner:
        if ARG_OLD not in runner:
            raise RuntimeError("Expected quota argument block not found")
        runner = runner.replace(ARG_OLD, ARG_NEW, 1)
    if "EBAY BATCH RESUME PLAN" not in runner:
        if ROOT_OLD not in runner:
            raise RuntimeError("Expected batch-root block not found")
        runner = runner.replace(ROOT_OLD, ROOT_NEW, 1)
    RUNNER_PATH.write_text(runner, encoding="utf-8")

    print("PHASE 10.6A3.1 EBAY RESUME PLANNING: APPLIED")
    print(f"Created: {RESUME_PATH.relative_to(ROOT)}")
    print(f"Updated: {RUNNER_PATH.relative_to(ROOT)}")
    print(f"Created: {TEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    apply()
