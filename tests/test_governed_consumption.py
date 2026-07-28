from terminal2.intelligence.governed_consumption import (
    decide_consumption,
    guarded_rank_score,
)


def test_current_asking_is_suppressed_from_models():
    decision = decide_consumption(
        {
            "valuation_state": "CURRENT_ASKING_REFERENCE_ONLY",
            "model_eligible": "false",
            "dashboard_eligible": "true",
        },
        {
            "forecast_eligible": "YES",
            "recommendation_eligible": "YES",
        },
    )
    assert decision.governed_forecast_eligible is False
    assert decision.governed_recommendation_eligible is False


def test_unavailable_is_suppressed():
    decision = decide_consumption(
        {
            "valuation_state": "VALUATION_UNAVAILABLE",
            "model_eligible": "false",
            "dashboard_eligible": "false",
        },
        None,
    )
    assert decision.governed_forecast_eligible is False


def test_direct_history_and_legacy_eligibility_pass():
    decision = decide_consumption(
        {
            "valuation_state": "DIRECT_HISTORY_VALUATION",
            "model_eligible": "true",
            "dashboard_eligible": "true",
        },
        {
            "forecast_eligible": "YES",
            "recommendation_eligible": "YES",
        },
    )
    assert decision.governed_forecast_eligible is True
    assert decision.governed_recommendation_eligible is True


def test_rank_score_uses_governed_current_price():
    score = guarded_rank_score(100, 150, "HIGH")
    assert score == 50.0
