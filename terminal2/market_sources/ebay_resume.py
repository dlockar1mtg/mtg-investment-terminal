from __future__ import annotations

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
