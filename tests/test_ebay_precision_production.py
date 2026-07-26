from __future__ import annotations

from pathlib import Path

from terminal2.market_sources import ebay_matching
from terminal2.market_sources import ebay_precision_production as production
from terminal2.market_sources import ebay_targeted_collection
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing


def test_universe_adapter_activates_and_restores_precision_matcher(monkeypatch) -> None:
    original = ebay_matching.match_listing
    observed: dict[str, object] = {}

    def fake_run_coverage(*, limit_per_product: int, max_products: int | None):
        observed["active_matcher"] = ebay_matching.match_listing
        observed["limit"] = limit_per_product
        observed["max_products"] = max_products
        return {"status": "PASS"}

    monkeypatch.setattr(ebay_matching, "run_coverage", fake_run_coverage)
    summary = production.run_precision_coverage(limit_per_product=7, max_products=2)

    assert observed["active_matcher"] is identity_match_listing
    assert observed["limit"] == 7
    assert observed["max_products"] == 2
    assert ebay_matching.match_listing is original
    assert summary["matcher_version"] == "precision-v2"
    assert summary["matcher_fail_closed"] is True


def test_targeted_adapter_activates_and_restores_precision_matcher(monkeypatch, tmp_path: Path) -> None:
    original = ebay_targeted_collection.match_listing
    product_map = tmp_path / "map.csv"
    product_map.write_text("tcgplayer_product_id\n1\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_run_targeted_coverage(*, product_map: Path, limit_per_product: int):
        observed["active_matcher"] = ebay_targeted_collection.match_listing
        observed["product_map"] = product_map
        observed["limit"] = limit_per_product
        return {"status": "PASS"}

    monkeypatch.setattr(
        ebay_targeted_collection,
        "run_targeted_coverage",
        fake_run_targeted_coverage,
    )
    summary = production.run_precision_targeted_coverage(
        product_map=product_map,
        limit_per_product=5,
    )

    assert observed["active_matcher"] is identity_match_listing
    assert observed["product_map"] == product_map
    assert observed["limit"] == 5
    assert ebay_targeted_collection.match_listing is original
    assert summary["matcher_version"] == "precision-v2"
    assert summary["matcher_fail_closed"] is True
