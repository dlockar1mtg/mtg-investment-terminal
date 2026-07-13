from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.forecast.engine import build_forecast_datasets
from terminal2.forecast.exports import publish_forecast_datasets
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class ForecastPublicationTests(unittest.TestCase):
    def test_publication(self):
        universe = pd.DataFrame({
            "investment_product_id": ["p1"],
            "box_name": ["Alpha"],
            "set_name": ["A"],
            "product_type": ["Collector Booster Display"],
            "current_price": [100.0],
            "investment_score": [80.0],
            "risk_adjusted_score": [78.0],
            "expected_cagr": [0.15],
            "projection_confidence": [80.0],
            "prob_loss": [0.15],
            "observation_count": [24],
            "return_30d": [0.05],
            "return_90d": [0.10],
            "return_180d": [0.18],
            "return_365d": [0.25],
            "annualized_volatility": [0.20],
            "trend_score": [80.0],
            "history_confidence": [90.0],
            "market_intelligence_score": [75.0],
            "market_intelligence_confidence": [70.0],
            "supply_signal_score": [70.0],
            "sales_velocity_score": [68.0],
            "liquidity_score": [72.0],
        })

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            result = build_forecast_datasets(universe)
            published = publish_forecast_datasets(
                result.datasets,
                warehouse=warehouse,
            )

            self.assertEqual(len(published), 6)
            self.assertTrue(
                (
                    root
                    / "data"
                    / "warehouse"
                    / "current"
                    / "intelligence"
                    / "forecast_product_summary.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
