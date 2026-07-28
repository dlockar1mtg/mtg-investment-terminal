from terminal2.market_sources.ebay_history_live import build_live_query
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


def test_live_booster_query_requires_magic_brand_prefix():
    assert build_live_query(query()).startswith("Magic The Gathering ")


def test_other_game_unlimited_box_is_rejected():
    row = classify_listing(
        query(),
        ReplayListing(
            item_id="1",
            title="Flesh and Blood Monarch Unlimited Edition Booster Box Factory Sealed",
            price=49.99,
            currency="USD",
            condition="New",
        ),
    )
    assert row.accepted is False
    assert "MTG_BRAND_SIGNAL_MISSING" in row.rejection_reason


def test_sorcery_beta_box_is_rejected():
    row = classify_listing(
        query("Beta Edition - Booster Box"),
        ReplayListing(
            item_id="2",
            title="Sorcery Contested Realm Beta Edition Booster Box New Factory Sealed",
            price=199.99,
            currency="USD",
            condition="New",
        ),
    )
    assert row.accepted is False
    assert "MTG_BRAND_SIGNAL_MISSING" in row.rejection_reason


def test_magic_unlimited_box_is_accepted():
    row = classify_listing(
        query(),
        ReplayListing(
            item_id="3",
            title="Magic The Gathering Unlimited Edition Booster Box Factory Sealed",
            price=250000.0,
            currency="USD",
            condition="New",
        ),
    )
    assert row.accepted is True
