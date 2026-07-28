from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "run_universal_mtg_ebay_history_pilot.py"
    spec = importlib.util.spec_from_file_location(
        "run_universal_mtg_ebay_history_pilot",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def product(index: int) -> dict[str, str]:
    return {
        "batch_id": "EBAY-HIST-001",
        "queue_rank": str(index),
        "canonical_product_id": f"P{index}",
        "canonical_product_name": f"Product {index}",
        "product_class": "PRE_COLLECTOR_BOOSTER_BOX",
        "normalized_ebay_query": f'"Product {index}" sealed booster box',
        "query_review_status": "APPROVED_FOR_DRY_RUN",
    }


def write_coverage(path: Path, product_id: str, state: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_product_id", "coverage_state"],
        )
        writer.writeheader()
        writer.writerow({
            "canonical_product_id": product_id,
            "coverage_state": state,
        })


def test_pilot_manifest_certifies_four_products(tmp_path: Path):
    module = load_module()
    detail, summary = module.build_execution_manifest(
        [product(i) for i in range(1, 5)],
        tmp_path,
    )
    assert summary["status"] == "PASS"
    assert summary["planned_products"] == 4
    assert summary["pending_products"] == 4
    assert summary["estimated_maximum_calls"] == 12
    assert all(
        row["live_collection_allowed"] == "false"
        for row in detail
    )


def test_resume_reuses_completed_product(tmp_path: Path):
    module = load_module()
    write_coverage(
        tmp_path / "ebay_product_coverage_test.csv",
        "P1",
        "MATCHED",
    )
    detail, summary = module.build_execution_manifest(
        [product(i) for i in range(1, 5)],
        tmp_path,
    )
    assert summary["completed_products"] == 1
    assert summary["pending_products"] == 3
    assert summary["estimated_maximum_calls"] == 9
    states = {
        row["canonical_product_id"]: row["execution_action"]
        for row in detail
    }
    assert states["P1"] == "SKIP_REUSE_COMPLETED"


def test_select_batch_is_deterministic():
    module = load_module()
    rows = [product(3), product(1), product(2), product(4)]
    selected = module.select_batch(rows, "EBAY-HIST-001")
    assert [
        row["canonical_product_id"] for row in selected
    ] == ["P1", "P2", "P3", "P4"]
