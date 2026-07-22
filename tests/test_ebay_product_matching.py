from __future__ import annotations

from terminal2.market_sources.ebay_matching import (
    CanonicalProduct,
    build_query,
    build_universe,
    classify_booster,
    match_listing,
)


def product(product_class: str = "COLLECTOR_BOOSTER_BOX") -> CanonicalProduct:
    return CanonicalProduct(
        canonical_product_id="MTG-TEST-1",
        canonical_product_name="Modern Horizons 3 Collector Booster Box",
        canonical_set_name="Modern Horizons 3",
        product_class=product_class,
        tcgplayer_product_id="1",
        release_date="2024-06-14",
        ebay_query="Magic The Gathering Modern Horizons 3 Collector Booster Box sealed",
    )


def test_classifies_only_desired_booster_boxes():
    assert classify_booster({"canonical_product_name": "Aether Revolt - Booster Box", "governed_release_date": "2017-01-20"}) == "PRE_COLLECTOR_BOOSTER_BOX"
    assert classify_booster({"canonical_product_name": "Modern Horizons 3 Collector Booster Box", "governed_release_date": "2024-06-14"}) == "COLLECTOR_BOOSTER_BOX"
    assert classify_booster({"canonical_product_name": "Modern Horizons 3 Play Booster Box", "governed_release_date": "2024-06-14"}) is None
    assert classify_booster({"canonical_product_name": "Wilds of Eldraine Draft Booster Box", "governed_release_date": "2023-09-08"}) is None


def test_query_is_generated_from_existing_product():
    query = build_query("Modern Horizons 3 - Collector Booster Box", "COLLECTOR_BOOSTER_BOX")
    assert "Modern Horizons 3 Collector Booster Box" in query
    assert query.endswith("sealed")


def test_exact_collector_box_listing_is_accepted():
    result = match_listing(product(), {
        "itemId": "v1|123|0",
        "title": "Magic The Gathering Modern Horizons 3 Collector Booster Box Factory Sealed",
        "price": {"value": "349.99", "currency": "USD"},
        "shippingOptions": [{"shippingCost": {"value": "10.00", "currency": "USD"}}],
        "seller": {"username": "seller"},
        "buyingOptions": ["FIXED_PRICE"],
        "condition": "New",
    }, "RUN", "2026-07-22T00:00:00Z")
    assert result.match_state == "ACCEPTED"
    assert result.landed_price == 359.99
    assert result.seller_hash


def test_pack_is_never_accepted():
    result = match_listing(product(), {
        "itemId": "v1|123|0",
        "title": "Modern Horizons 3 Collector Booster Pack Single Pack Sealed",
        "price": {"value": "34.99", "currency": "USD"},
    }, "RUN", "2026-07-22T00:00:00Z")
    assert result.match_state == "REJECTED"
    assert "excluded_product_form" in result.exclusion_reasons


def test_case_and_presale_are_not_accepted():
    result = match_listing(product(), {
        "itemId": "v1|123|0",
        "title": "PREORDER Modern Horizons 3 Collector Booster Sealed Case of 6 Boxes",
        "price": {"value": "1999.99", "currency": "USD"},
    }, "RUN", "2026-07-22T00:00:00Z")
    assert result.match_state == "REJECTED"
    assert "presale" in result.exclusion_reasons
    assert "excluded_product_form" in result.exclusion_reasons


def test_secret_lair_requires_secret_lair_identity():
    secret = CanonicalProduct("SL-1", "Festival in a Box", "Secret Lair", "SEALED_SECRET_LAIR", "", "", "query")
    result = match_listing(secret, {
        "itemId": "1",
        "title": "Magic The Gathering Festival in a Box sealed",
        "price": {"value": "200", "currency": "USD"},
    }, "RUN", "2026-07-22T00:00:00Z")
    assert result.match_state != "ACCEPTED"


def test_real_governed_universe_contains_only_allowed_classes():
    universe = build_universe()
    assert universe
    assert {row.product_class for row in universe} <= {
        "COLLECTOR_BOOSTER_BOX",
        "PRE_COLLECTOR_BOOSTER_BOX",
        "SEALED_SECRET_LAIR",
    }
    names = "\n".join(row.canonical_product_name.lower() for row in universe)
    assert "play booster box" not in names
    assert "set booster box" not in names
    assert "jumpstart booster box" not in names
