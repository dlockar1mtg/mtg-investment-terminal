from datetime import date

from terminal2.market_sources.universal_market_valuation import choose_valuation


def test_direct_history_has_priority_over_asking():
    decision = choose_valuation(
        {
            "consolidated_market_price": "100",
            "observation_date": "2026-07-01",
        },
        {
            "median_price": "150",
            "observation_date": "2026-07-28",
        },
        date(2026, 7, 28),
    )
    assert decision.selected_reference_price == 100
    assert decision.selected_source_type == "DIRECT_HISTORICAL_MARKET"
    assert decision.model_eligible is True


def test_current_asking_is_reference_only():
    decision = choose_valuation(
        None,
        {
            "median_price": "150",
            "observation_date": "2026-07-28",
        },
        date(2026, 7, 28),
    )
    assert decision.valuation_state == "CURRENT_ASKING_REFERENCE_ONLY"
    assert decision.model_eligible is False
    assert decision.dashboard_eligible is True


def test_missing_price_is_unavailable():
    decision = choose_valuation(None, None, date(2026, 7, 28))
    assert decision.selected_reference_price is None
    assert decision.valuation_state == "VALUATION_UNAVAILABLE"
