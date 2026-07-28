from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "audit_universal_mtg_ebay_history_queries.py"
    spec = importlib.util.spec_from_file_location(
        "audit_universal_mtg_ebay_history_queries",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_short_clean_query_is_approved_for_dry_run():
    module = load_module()
    result = module.audit_query({
        "canonical_product_id": "A",
        "canonical_product_name": "Alpha",
        "batch_id": "B1",
        "priority_tier": "P2",
        "ebay_query": '"Alpha Booster Box" sealed',
    })
    assert result["query_review_status"] == "APPROVED_FOR_DRY_RUN"
    assert result["live_collection_allowed"] == "false"


def test_long_query_requires_review():
    module = load_module()
    result = module.audit_query({
        "canonical_product_id": "A",
        "canonical_product_name": "Long",
        "batch_id": "B1",
        "priority_tier": "P2",
        "ebay_query": '"' + ("x" * 110) + '" sealed',
    })
    assert result["query_review_status"] == "REVIEW_REQUIRED"
    assert "QUERY_OVER_100_CHARACTERS" in result["review_reasons"]


def test_normalized_collision_is_detected():
    module = load_module()
    rows = [
        {
            "canonical_product_id": "A",
            "canonical_product_name": "A",
            "batch_id": "B1",
            "priority_tier": "P2",
            "ebay_query": '"Alpha-Beta" sealed',
        },
        {
            "canonical_product_id": "B",
            "canonical_product_name": "B",
            "batch_id": "B1",
            "priority_tier": "P2",
            "ebay_query": '"Alpha Beta" sealed',
        },
    ]
    audited, summary = module.build_audit(rows)
    assert all(
        row["query_review_status"] == "REVIEW_REQUIRED"
        for row in audited
    )
    assert summary["normalized_query_collisions"] == 1
