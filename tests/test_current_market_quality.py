from terminal2.market_sources.current_market_quality import (
    evaluate_identity,
    robust_snapshot,
)

def test_distinct_product_identity_is_auto_approved():
    result = evaluate_identity(
        "Commander Deck: Raining Cats and Dogs — Standard Edition",
        "MTG Secret Lair Raining Cats and Dogs Commander Deck Factory Sealed",
    )
    assert result.quality_state == "AUTO_APPROVED"

def test_generic_bundle_title_requires_review_or_rejection():
    result = evaluate_identity(
        "Full Bundle — Standard Edition",
        "MTG Secret Lair Full Bundle Factory Sealed",
    )
    assert result.quality_state != "AUTO_APPROVED"

def test_unrelated_title_is_rejected():
    result = evaluate_identity(
        "Commander Deck: Goblin Storm — Standard Edition",
        "MTG Commander Masters Collector Booster Box Factory Sealed",
    )
    assert result.quality_state == "REJECTED_IDENTITY"

def test_robust_snapshot():
    result = robust_snapshot([10.0, 20.0, 30.0])
    assert result["listing_count"] == 3
    assert result["median_price"] == 20.0
