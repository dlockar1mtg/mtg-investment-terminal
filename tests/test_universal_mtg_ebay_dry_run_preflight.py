from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_mtg_ebay_dry_run_preflight.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_mtg_ebay_dry_run_preflight",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def row(index: int, batch_id: str = "B1") -> dict[str, str]:
    return {
        "batch_id": batch_id,
        "batch_sequence": "1",
        "batch_label": "Pilot",
        "canonical_product_id": f"P{index}",
        "canonical_product_name": f"Product {index}",
        "product_class": "SECRET_LAIR",
        "priority_tier": "P2_MEDIUM",
        "normalized_ebay_query": f'"Product {index}" sealed',
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


def test_preflight_estimates_pending_calls(tmp_path: Path):
    module = load_module()
    details, batches, _ = module.build_preflight(
        [row(1), row(2)],
        tmp_path,
        simulated_quota_remaining=5000,
        quota_reserve=100,
        maximum_queries_per_product=3,
    )
    assert batches[0]["pending_products"] == 2
    assert batches[0]["estimated_maximum_calls"] == 6
    assert all(item["resume_state"] == "PENDING" for item in details)


def test_resume_completed_product_reduces_calls(tmp_path: Path):
    module = load_module()
    write_coverage(
        tmp_path / "B1" / "ebay_product_coverage_test.csv",
        "P1",
        "MATCHED",
    )
    details, batches, _ = module.build_preflight(
        [row(1), row(2)],
        tmp_path,
        simulated_quota_remaining=5000,
        quota_reserve=100,
        maximum_queries_per_product=3,
    )
    assert batches[0]["completed_products"] == 1
    assert batches[0]["pending_products"] == 1
    assert batches[0]["estimated_maximum_calls"] == 3
    assert {
        item["canonical_product_id"]: item["resume_state"]
        for item in details
    }["P1"] == "COMPLETED"


def test_insufficient_simulated_quota_blocks_dry_run(tmp_path: Path):
    module = load_module()
    _, batches, _ = module.build_preflight(
        [row(1), row(2)],
        tmp_path,
        simulated_quota_remaining=105,
        quota_reserve=100,
        maximum_queries_per_product=3,
    )
    assert batches[0]["quota_supported"] == "false"
    assert batches[0]["dry_run_allowed"] == "false"
    assert batches[0]["live_collection_allowed"] == "false"
