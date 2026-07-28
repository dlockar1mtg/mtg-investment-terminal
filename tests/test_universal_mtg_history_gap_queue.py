from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_mtg_history_gap_queue.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_mtg_history_gap_queue",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ambiguous_ebay_gap_is_highest_priority():
    module = load_module()
    category, action, score = module.classify_gap(
        {"history_completion_route": "EBAY_ACCUMULATION_REQUIRED"},
        {
            "tcgcsv_identity_status": "TCGCSV_ID_AMBIGUOUS",
            "tcgcsv_archive_eligible": "false",
            "ebay_history_eligible": "true",
        },
    )
    assert category == "IDENTITY_AMBIGUOUS_EBAY_ACCUMULATION"
    assert "Review identity" in action
    assert score == 95


def test_archive_eligible_no_observations_gets_fallback():
    module = load_module()
    category, action, score = module.classify_gap(
        {"history_completion_route": "ARCHIVE_HISTORY_NOT_AVAILABLE"},
        {
            "tcgcsv_identity_status": "TCGCSV_ID_CONFIRMED",
            "tcgcsv_archive_eligible": "true",
            "ebay_history_eligible": "true",
        },
    )
    assert category == "ARCHIVE_ELIGIBLE_NO_OBSERVATIONS"
    assert "eBay fallback" in action
    assert score == 80


def test_build_queue_only_includes_zero_history_products():
    module = load_module()
    completion = [
        {
            "canonical_product_id": "A",
            "canonical_product_name": "A",
            "product_class": "SECRET_LAIR",
            "history_verification_status": "NO_DIRECT_HISTORY",
            "history_completion_route": "EBAY_ACCUMULATION_REQUIRED",
            "distinct_history_dates": "0",
        },
        {
            "canonical_product_id": "B",
            "canonical_product_name": "B",
            "product_class": "SECRET_LAIR",
            "history_verification_status": "HISTORY_1_DATE",
            "history_completion_route": "DIRECT_HISTORY_AVAILABLE",
            "distinct_history_dates": "1",
        },
    ]
    routing = [
        {
            "universal_mtg_product_id": "A",
            "tcgcsv_identity_status": "TCGCSV_ID_NOT_FOUND",
            "tcgcsv_archive_eligible": "false",
            "ebay_history_eligible": "true",
            "primary_history_route": "EBAY_DAILY_ACCUMULATION",
        },
        {
            "universal_mtg_product_id": "B",
            "tcgcsv_identity_status": "TCGCSV_ID_CONFIRMED",
            "tcgcsv_archive_eligible": "true",
            "ebay_history_eligible": "true",
            "primary_history_route": "TCGCSV_MONTHLY_ARCHIVE",
        },
    ]
    queue, _, summary = module.build_queue(completion, routing)
    assert [row["canonical_product_id"] for row in queue] == ["A"]
    assert summary["gap_queue_rows"] == 1
