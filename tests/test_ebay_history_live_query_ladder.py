from terminal2.market_sources.ebay_history_live import (
    LiveBrowseHistoryCollector,
    build_live_query_ladder,
)
from terminal2.market_sources.ebay_history_pipeline import HistoryQuery


def query(name: str = "Unlimited Edition - Booster Box"):
    return HistoryQuery(
        canonical_product_id="P1",
        canonical_product_name=name,
        product_class="PRE_COLLECTOR_BOOSTER_BOX",
        query=f'"{name}" sealed booster box',
    )


def test_live_query_ladder_has_three_magic_specific_queries():
    ladder = build_live_query_ladder(query())
    assert len(ladder) == 3
    assert ladder[0] == 'Magic The Gathering "Unlimited Edition" booster box'
    assert ladder[1] == 'MTG "Unlimited Edition" booster box'
    assert ladder[2] == 'Magic "Unlimited Edition" sealed box'


class FakeLadderClient:
    def __init__(self):
        self.queries = []

    def search(self, query: str, limit: int):
        self.queries.append(query)
        if query.startswith("MTG "):
            return [{
                "itemId": "mtg-1",
                "title": (
                    "MTG Unlimited Edition Booster Box "
                    "Factory Sealed"
                ),
                "price": {"value": "250000", "currency": "USD"},
                "condition": "New",
            }]
        return []


def test_live_collector_uses_query_ladder_and_deduplicates():
    client = FakeLadderClient()
    collector = LiveBrowseHistoryCollector(client=client, limit=20)
    rows = collector.collect(query())
    assert len(client.queries) == 3
    assert len(rows) == 1
    assert rows[0].item_id == "mtg-1"
