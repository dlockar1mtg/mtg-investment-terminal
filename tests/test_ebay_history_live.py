from __future__ import annotations

from terminal2.market_sources.ebay_history_live import (
    LiveBrowseHistoryCollector,
    browse_item_to_replay,
    collect_live_product,
)
from terminal2.market_sources.ebay_history_pipeline import HistoryQuery


class FakeClient:
    def search(self, query: str, limit: int):
        return [{
            "itemId": "1",
            "title": "Magic The Gathering Alpha Edition sealed booster box",
            "price": {"value": "1000.00", "currency": "USD"},
            "condition": "New",
        }]


def query():
    return HistoryQuery(
        canonical_product_id="P1",
        canonical_product_name="Alpha Edition - Booster Box",
        product_class="PRE_COLLECTOR_BOOSTER_BOX",
        query='"Alpha Edition - Booster Box" sealed booster box',
    )


def test_browse_item_adapter_maps_price_and_currency():
    row = browse_item_to_replay(FakeClient().search("x", 1)[0])
    assert row.price == 1000.0
    assert row.currency == "USD"


def test_live_collector_uses_exact_normalized_query():
    collector = LiveBrowseHistoryCollector(client=FakeClient(), limit=20)
    rows = collector.collect(query())
    assert len(rows) == 1


def test_live_product_result_is_matched():
    collector = LiveBrowseHistoryCollector(client=FakeClient(), limit=20)
    classified, result = collect_live_product(query(), collector)
    assert result.coverage_state == "MATCHED"
    assert result.accepted_listing_count == 1
    assert classified[0].accepted is True
