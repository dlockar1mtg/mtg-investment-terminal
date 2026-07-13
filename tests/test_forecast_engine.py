import unittest

import pandas as pd

from terminal2.forecast.engine import build_forecast_datasets


class ForecastEngineTests(unittest.TestCase):
    def setUp(self):
        self.universe = pd.DataFrame({
            "investment_product_id": ["p1", "p2"],
            "box_name": ["Alpha", "Beta"],
            "set_name": ["A", "B"],
            "product_type": [
                "Collector Booster Display",
                "Draft Booster Display",
            ],
            "current_price": [100.0, 200.0],
            "investment_score": [80.0, 60.0],
            "risk_adjusted_score": [78.0, 58.0],
            "expected_cagr": [0.15, 0.08],
            "projection_confidence": [80.0, 55.0],
            "prob_loss": [0.15, 0.35],
            "observation_count": [24, 12],
            "return_30d": [0.05, -0.03],
            "return_90d": [0.10, -0.05],
            "return_180d": [0.18, -0.08],
            "return_365d": [0.25, -0.10],
            "annualized_volatility": [0.20, 0.40],
            "trend_score": [80.0, 35.0],
            "history_confidence": [90.0, 55.0],
            "market_intelligence_score": [75.0, 45.0],
            "market_intelligence_confidence": [70.0, 40.0],
            "supply_signal_score": [70.0, 45.0],
            "sales_velocity_score": [68.0, 42.0],
            "liquidity_score": [72.0, 48.0],
        })

    def test_builds_all_forecast_datasets(self):
        result = build_forecast_datasets(self.universe)
        datasets = result.datasets

        self.assertEqual(len(datasets), 6)
        self.assertEqual(
            len(datasets["forecast_horizons"]),
            len(self.universe) * 4,
        )
        self.assertEqual(
            len(datasets["forecast_product_summary"]),
            len(self.universe),
        )
        self.assertEqual(
            datasets["forecast_rankings"].iloc[0][
                "investment_product_id"
            ],
            "p1",
        )

    def test_forecast_ranges_are_ordered(self):
        horizons = build_forecast_datasets(
            self.universe
        ).datasets["forecast_horizons"]
        self.assertTrue(
            (
                horizons["bear_forecast_price"]
                <= horizons["base_forecast_price"]
            ).all()
        )
        self.assertTrue(
            (
                horizons["base_forecast_price"]
                <= horizons["bull_forecast_price"]
            ).all()
        )


if __name__ == "__main__":
    unittest.main()
