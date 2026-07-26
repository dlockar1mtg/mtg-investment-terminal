from __future__ import annotations

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v2 import identity_match_listing


def product(name: str, product_class: str = "COLLECTOR_BOOSTER_BOX") -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="TEST",
        canonical_product_name=name,
        canonical_set_name=name,
        product_class=product_class,
        tcgplayer_product_id="1",
        release_date="2025-01-01",
        ebay_query="query",
    )


def listing(title: str) -> dict[str, object]:
    return {
        "itemId": "1",
        "title": title,
        "price": {"value": "100.00", "currency": "USD"},
        "condition": "New/Factory Sealed",
    }


def classify(name: str, title: str, product_class: str = "COLLECTOR_BOOSTER_BOX"):
    return identity_match_listing(
        product(name, product_class),
        listing(title),
        "RUN",
        "2026-07-26T00:00:00Z",
    )


def test_complete_four_pack_collector_display_is_not_rejected_as_incomplete() -> None:
    result = classify(
        "Commander Masters - Collector Booster Box",
        "MTG Commander Masters Collector Booster Box 4 Packs English Factory Sealed",
    )
    assert result.match_state != "REJECTED"
    assert "incomplete_pack_box_lot" not in result.exclusion_reasons


def test_complete_twelve_pack_collector_display_is_not_rejected_as_incomplete() -> None:
    result = classify(
        "Modern Horizons 3 - Collector Booster Display",
        "MTG Modern Horizons 3 Collector Booster Box 12 Packs English Factory Sealed",
    )
    assert result.match_state != "REJECTED"
    assert "incomplete_pack_box_lot" not in result.exclusion_reasons


def test_complete_thirty_six_pack_draft_display_is_not_rejected_as_incomplete() -> None:
    result = classify(
        "Wilds of Eldraine Draft Booster Display",
        "MTG Wilds of Eldraine Draft Booster Box 36 Packs Factory Sealed",
        "PRE_COLLECTOR_BOOSTER_BOX",
    )
    assert "incomplete_pack_box_lot" not in result.exclusion_reasons


def test_partial_pack_plus_box_lot_remains_rejected() -> None:
    result = classify(
        "Chronicles - Booster Box",
        "Magic Chronicles Booster Box lot of 26 packs plus box",
        "PRE_COLLECTOR_BOOSTER_BOX",
    )
    assert result.match_state == "REJECTED"
    assert "incomplete_pack_box_lot" in result.exclusion_reasons


def test_single_pack_remains_rejected() -> None:
    result = classify(
        "Edge of Eternities - Collector Booster Display",
        "MTG Edge of Eternities Collector Booster Box Sealed 1 Pack",
    )
    assert result.match_state == "REJECTED"
    assert "single_pack_collector_product" in result.exclusion_reasons
