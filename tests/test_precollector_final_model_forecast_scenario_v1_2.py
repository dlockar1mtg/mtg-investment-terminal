import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_final_model_forecast_scenario_v1_2.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_amendment_is_explicit():
    contract = load()

    assert contract["contract_version"] == "1.2.0"

    assert (
        contract["amendment_reason"]
        ==
        "GOVERN_CURRENT_PRICE_AUTHORITY_GAPS_DURING_PRODUCTION_FORECAST"
    )


def test_current_price_authority_counts():
    current = load()["current_price_authority"]

    assert current["governed_price_coverage_products"] == 121
    assert current["canonical_products_without_governed_current_price"] == 10


def test_missing_current_price_becomes_gap():
    current = load()["current_price_authority"]

    assert current["missing_current_price_behavior"] == "FORECAST_GAP"
    assert current["invalid_current_price_behavior"] == "FORECAST_GAP"
    assert current["nonpositive_current_price_behavior"] == "FORECAST_GAP"


def test_price_gap_is_not_exclusion():
    current = load()["current_price_authority"]

    assert (
        current["current_price_gap_causes_canonical_removal"]
        is False
    )

    assert (
        current["current_price_gap_causes_persistent_model_exclusion"]
        is False
    )


def test_holdout_governance_preserved():
    holdout = load()["product_holdout"]

    assert holdout["required_dispositions"] == 115
    assert holdout["persistent_exclusions"] == 0

    assert (
        holdout["no_valid_prediction_causes_exclusion"]
        is False
    )


def test_long_horizon_labels_preserved():
    long_horizon = load()["long_horizon"]

    assert long_horizon["direct_3_year_backtest"] is False
    assert long_horizon["direct_5_year_backtest"] is False


def test_monte_carlo_still_next_stage():
    authorization = load()["authorization"]

    assert authorization["monte_carlo_in_this_stage"] is False
    assert authorization["monte_carlo_after_success"] is True
    assert authorization["purchase_ranking_in_this_stage"] is False