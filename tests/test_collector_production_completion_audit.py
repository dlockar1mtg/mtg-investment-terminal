from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_collector_production_completion.py"

spec = importlib.util.spec_from_file_location(
    "audit_collector_production_completion",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_product_id_supports_governed_identity_fields() -> None:
    assert module.product_id({"investment_product_id": "A"}) == "A"
    assert module.product_id({"canonical_product_id": "B"}) == "B"
    assert module.product_id({"asset_id": "C"}) == "C"


def test_collector_classification_excludes_non_display_configurations() -> None:
    assert module.is_collector_row(
        {
            "product_lane": "COLLECTOR_BOOSTER",
            "product_name": "Example Collector Booster Display",
        }
    )
    assert not module.is_collector_row(
        {
            "product_lane": "COLLECTOR_BOOSTER",
            "product_name": "Example Collector Booster Case",
        }
    )
    assert not module.is_collector_row(
        {
            "product_name": "Example Collector Booster Pack",
        }
    )


def test_index_unique_reports_duplicates_without_fixed_counts() -> None:
    indexed, issues = module.index_unique(
        [
            {"investment_product_id": "A"},
            {"investment_product_id": "B"},
            {"investment_product_id": "B"},
        ],
        "sample",
    )
    assert set(indexed) == {"A", "B"}
    assert issues == [
        {
            "dataset": "sample",
            "product_id": "B",
            "issue": "DUPLICATE_PRODUCT_ID",
        }
    ]


def test_supported_methods_cover_current_collector_routes() -> None:
    assert {
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED",
        "FUNDAMENTAL_COMPARABLE_HYBRID",
    }.issubset(module.SUPPORTED_METHODS)
