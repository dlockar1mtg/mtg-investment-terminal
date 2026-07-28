from terminal2.market_sources.ebay_history_live import build_live_query_ladder
from terminal2.market_sources.ebay_history_pipeline import (
    HistoryQuery,
    ReplayListing,
    classify_listing,
)


def query(name: str = "Unlimited Edition - Booster Box"):
    return HistoryQuery(
        canonical_product_id="P1",
        canonical_product_name=name,
        product_class="PRE_COLLECTOR_BOOSTER_BOX",
        query=f'"{name}" sealed booster box',
    )


def test_query_ladder_is_magic_specific():
    ladder = build_live_query_ladder(query())
    assert len(ladder) == 3
    assert all("Magic" in value or value.startswith("MTG ") for value in ladder)


def test_cross_game_listing_is_rejected():
    row = classify_listing(
        query(),
        ReplayListing(
            item_id="1",
            title="Flesh and Blood Unlimited Edition Booster Box Factory Sealed",
            price=49.99,
            currency="USD",
            condition="New",
        ),
    )
    assert row.accepted is False
    assert "MTG_BRAND_SIGNAL_MISSING" in row.rejection_reason


def test_magic_listing_is_accepted():
    row = classify_listing(
        query(),
        ReplayListing(
            item_id="2",
            title="Magic The Gathering Unlimited Edition Booster Box Factory Sealed",
            price=250000.0,
            currency="USD",
            condition="New",
        ),
    )
    assert row.accepted is True
