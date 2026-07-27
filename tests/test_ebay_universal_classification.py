from __future__ import annotations

import pytest

from terminal2.market_sources.ebay_matching import CanonicalProduct
from terminal2.market_sources.ebay_precision_v3 import identity_match_listing
from terminal2.market_sources.ebay_universal_classification import classify_listing_identity


@pytest.mark.parametrize(
    ("product_name", "product_class", "title", "expected"),
    [
        (
            "FINAL FANTASY - Collector Booster Display (Japanese)",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Final Fantasy Japanese Collector Booster Box Factory Sealed",
            "ACCEPTED",
        ),
        (
            "FINAL FANTASY - Collector Booster Display (Japanese)",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Final Fantasy English Collector Booster Box Factory Sealed",
            "REJECTED",
        ),
        (
            "FINAL FANTASY - Collector Booster Display (Japanese)",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Final Fantasy Collector Booster Box Factory Sealed",
            "REVIEW",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Collector Booster Box 12 Packs Factory Sealed",
            "ACCEPTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Single Collector Booster Pack Factory Sealed",
            "REJECTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Factory Sealed Case of 6 Collector Booster Boxes",
            "REJECTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Collector Booster Empty Box Only",
            "REJECTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Collector Booster Box Opened Packs Removed",
            "REJECTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Collector Booster Box Damaged Factory Sealed",
            "REJECTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Collector Product Factory Sealed",
            "REVIEW",
        ),
        (
            "Artist Series: Example — Traditional Foil Edition",
            "SEALED_SECRET_LAIR",
            "MTG Secret Lair Artist Series Example Traditional Foil Factory Sealed",
            "ACCEPTED",
        ),
        (
            "Artist Series: Example — Traditional Foil Edition",
            "SEALED_SECRET_LAIR",
            "MTG Secret Lair Artist Series Example Traditional Foil Single Card",
            "REJECTED",
        ),
        (
            "Artist Series: Example — Traditional Foil Edition",
            "SEALED_SECRET_LAIR",
            "MTG Secret Lair Artist Series Example Traditional Foil Deck Box",
            "REJECTED",
        ),
        (
            "Artist Series: Example — Traditional Foil Edition",
            "SEALED_SECRET_LAIR",
            "MTG Secret Lair Artist Series Example Traditional Foil",
            "REVIEW",
        ),
        (
            "Wilds of Eldraine Draft Booster Display",
            "PRE_COLLECTOR_BOOSTER_BOX",
            "MTG Wilds of Eldraine Draft Booster Box 36 Packs Factory Sealed",
            "ACCEPTED",
        ),
        (
            "Wilds of Eldraine Draft Booster Display",
            "PRE_COLLECTOR_BOOSTER_BOX",
            "MTG Wilds of Eldraine Draft Booster Partial Box Missing Packs",
            "REJECTED",
        ),
        (
            "Commander Masters - Collector Booster Box",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Commander Masters Japanese Collector Booster Box Factory Sealed",
            "REVIEW",
        ),
    ],
)
def test_universal_classification_matrix(
    product_name: str,
    product_class: str,
    title: str,
    expected: str,
) -> None:
    result = classify_listing_identity(product_name, product_class, title)
    assert result.decision == expected
    assert result.audit_tags
    assert result.listing_identity.product_form
    assert result.listing_identity.language


def _product(name: str, product_class: str) -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="TEST",
        canonical_product_name=name,
        canonical_set_name=name,
        product_class=product_class,
        tcgplayer_product_id="1",
        release_date="2025-01-01",
        ebay_query="query",
    )


def _listing(title: str) -> dict[str, object]:
    return {
        "itemId": "1",
        "title": title,
        "price": {"value": "100.00", "currency": "USD"},
        "condition": "New/Factory Sealed",
    }


@pytest.mark.parametrize(
    ("name", "product_class", "title", "expected"),
    [
        (
            "FINAL FANTASY - Collector Booster Display (Japanese)",
            "COLLECTOR_BOOSTER_BOX",
            "Magic The Gathering FINAL FANTASY Japanese Collector Booster Box Factory Sealed",
            "ACCEPTED",
        ),
        (
            "FINAL FANTASY - Collector Booster Display (Japanese)",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Final Fantasy Collector Booster Box English Factory Sealed",
            "REJECTED",
        ),
        (
            "Modern Horizons 3 - Collector Booster Display",
            "COLLECTOR_BOOSTER_BOX",
            "MTG Modern Horizons 3 Collector Booster Empty Box Only",
            "REJECTED",
        ),
        (
            "Artist Series: Example — Traditional Foil Edition",
            "SEALED_SECRET_LAIR",
            "MTG Secret Lair Artist Series Example Traditional Foil Factory Sealed",
            "ACCEPTED",
        ),
    ],
)
def test_precision_v3_integration_matrix(
    name: str,
    product_class: str,
    title: str,
    expected: str,
) -> None:
    result = identity_match_listing(
        _product(name, product_class),
        _listing(title),
        "RUN",
        "2026-07-27T00:00:00Z",
    )
    assert result.match_state == expected
    assert "universal_policy_decision:" in result.exclusion_reasons
    assert "universal_listing_form:" in result.exclusion_reasons
