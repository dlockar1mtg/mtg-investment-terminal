from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_mtg_ebay_accumulation_batches.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_mtg_ebay_accumulation_batches",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_row(
    index: int,
    product_class: str,
    priority: str,
) -> dict[str, str]:
    return {
        "queue_rank": str(index),
        "canonical_product_id": f"P{index}",
        "canonical_product_name": f"Product {index}",
        "product_class": product_class,
        "priority_tier": priority,
        "priority_score": "80",
        "gap_category": "TEST",
        "tcgcsv_identity_status": "TEST",
        "identity_review_required": "false",
        "archive_recheck_required": "false",
        "ebay_accumulation_required": "true",
        "accumulation_target_dates": "30",
    }


def test_query_is_exact_and_sealed():
    module = load_module()
    query, strategy = module.build_query(
        make_row(1, "SECRET_LAIR", "P2_MEDIUM")
    )
    assert query == '"Product 1" sealed'
    assert strategy == "EXACT_NAME_SEALED_SECRET_LAIR"


def test_batch_plan_matches_governed_sizes():
    module = load_module()
    rows = []
    rank = 1
    for _ in range(4):
        rows.append(make_row(rank, "PRE_COLLECTOR_BOOSTER_BOX", "P2_MEDIUM"))
        rank += 1
    for _ in range(46):
        rows.append(make_row(rank, "SECRET_LAIR", "P2_MEDIUM"))
        rank += 1
    for _ in range(52):
        rows.append(make_row(rank, "SECRET_LAIR", "P1_HIGH"))
        rank += 1
    for _ in range(50):
        rows.append(make_row(rank, "SECRET_LAIR", "P0_CRITICAL"))
        rank += 1

    planned = module.assign_batches(rows)
    _, summary = module.summarize(planned)

    assert summary["status"] == "PASS"
    assert summary["planned_products"] == 152
    assert summary["planned_batches"] == 7
    assert summary["live_collection_enabled"] is False


def test_all_planned_rows_are_live_disabled():
    module = load_module()
    planned = module.assign_batches([
        make_row(1, "PRE_COLLECTOR_BOOSTER_BOX", "P2_MEDIUM")
    ])
    assert all(
        row["live_collection_allowed"] == "false"
        for row in planned
    )
