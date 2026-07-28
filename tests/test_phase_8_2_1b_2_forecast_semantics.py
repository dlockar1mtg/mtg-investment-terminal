from __future__ import annotations

from scripts.repair_phase_8_2_1b_2_forecast_semantics import (
    FORECAST_METHOD,
    clear_horizons,
    native_values,
    repair_uip_forecast,
)


def test_native_values_use_market_and_monte_carlo_fields() -> None:
    values = native_values(
        {
            "current_price": "227.18",
            "mc_p05": "261.31",
            "mc_median": "340.58",
            "mc_p95": "444.19",
        }
    )
    assert values == {
        "current": "227.18",
        "low": "261.31",
        "base": "340.58",
        "high": "444.19",
    }


def test_uip_forecast_repair_removes_false_horizon_values() -> None:
    row = {
        "current_market_value_usd": "825",
        "forecast_method": "TIER_GUARDED_SCENARIO_BANDS",
        "one_year_base_usd": "891",
        "three_year_base_usd": "1031.25",
        "five_year_base_usd": "1196.25",
    }
    repair_uip_forecast(
        row,
        {
            "current": "227.18",
            "low": "261.31",
            "base": "340.58",
            "high": "444.19",
        },
    )
    assert row["current_market_value_usd"] == "227.18"
    assert row["forecast_method"] == FORECAST_METHOD
    assert row["native_forecast_base_usd"] == "340.58"
    assert row["one_year_base_usd"] == ""
    assert row["three_year_base_usd"] == ""
    assert row["five_year_base_usd"] == ""


def test_clear_horizons_is_fail_closed() -> None:
    row = {
        "one_year_downside_usd": "1",
        "one_year_base_usd": "2",
        "one_year_upside_usd": "3",
        "expected_return": "2.02",
        "forecast_horizon_months": "12",
    }
    clear_horizons(row)
    assert all(value == "" for value in row.values())
