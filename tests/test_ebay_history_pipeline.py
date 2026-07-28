from __future__ import annotations

from terminal2.market_sources.ebay_history_pipeline import (
    HistoryQuery,
    OfflineReplayCollector,
    classify_listing,
    consolidate_observations,
    ReplayListing,
    run_offline_replay,
)


def query() -> HistoryQuery:
    return HistoryQuery(
        canonical_product_id="P1",
        canonical_product_name="Alpha Edition - Booster Box",
        product_class="PRE_COLLECTOR_BOOSTER_BOX",
        query='"Alpha Edition - Booster Box" sealed booster box',
    )


def test_valid_sealed_box_is_accepted():
    row = classify_listing(
        query(),
        ReplayListing(
            item_id="1",
            title="Magic The Gathering Alpha Edition sealed booster box",
            price=1000.0,
            currency="USD",
            condition="New",
        ),
    )
    assert row.accepted is True


def test_opened_box_and_single_pack_are_rejected():
    opened = classify_listing(
        query(),
        ReplayListing(
            item_id="2",
            title="Alpha Edition opened empty box",
            price=50.0,
            currency="USD",
            condition="Used",
        ),
    )
    pack = classify_listing(
        query(),
        ReplayListing(
            item_id="3",
            title="Alpha Edition single pack sealed",
            price=25.0,
            currency="USD",
            condition="New",
        ),
    )
    assert opened.accepted is False
    assert "OPENED_OR_EMPTY" in opened.rejection_reason
    assert pack.accepted is False
    assert "SINGLE_PACK" in pack.rejection_reason


def test_offline_replay_sets_matched_state():
    collector = OfflineReplayCollector({
        "P1": [{
            "item_id": "1",
            "title": "Magic The Gathering Alpha Edition sealed booster box",
            "price": 1000.0,
            "currency": "USD",
            "condition": "New",
        }]
    })
    _, summary = run_offline_replay([query()], collector)
    assert summary["coverage_states"] == {"MATCHED": 1}
    assert summary["live_collection_enabled"] is False


def test_consolidation_deduplicates_product_date():
    row = {
        "canonical_product_id": "P1",
        "observation_date": "2026-07-28",
        "market_price": "1000.00",
    }
    consolidated = consolidate_observations([[row], [row]])
    assert len(consolidated) == 1
