from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.intelligence.engine import (
    build_core_intelligence_datasets,
)
from terminal2.intelligence.exports import (
    publish_intelligence_datasets,
)
from terminal2.warehouse_core import (
    Warehouse,
    get_warehouse_config,
)


class CoreIntelligencePublicationTests(unittest.TestCase):
    def test_publication(self):
        universe = pd.DataFrame(
            [
                {
                    "investment_product_id": "P1",
                    "box_name": "Example",
                    "set_name": "Set",
                    "product_type": "Collector Booster Display",
                    "current_price": 200.0,
                    "investment_score": 70.0,
                    "risk_adjusted_score": 68.0,
                    "expected_cagr": 0.12,
                    "projection_confidence": 80.0,
                    "prob_loss": 0.20,
                    "observation_count": 24,
                    "return_30d": 0.03,
                    "return_90d": 0.08,
                    "return_180d": 0.12,
                    "return_365d": 0.20,
                    "annualized_volatility": 0.25,
                    "trend_score": 70.0,
                    "history_confidence": 80.0,
                    "market_intelligence_score": 72.0,
                    "market_intelligence_confidence": 75.0,
                    "supply_signal_score": 70.0,
                    "sales_velocity_score": 65.0,
                    "liquidity_score": 75.0,
                }
            ]
        )
        datasets = build_core_intelligence_datasets(
            universe
        ).datasets

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            published = publish_intelligence_datasets(
                datasets,
                warehouse=warehouse,
            )
            self.assertEqual(len(published), 7)
            self.assertTrue(
                (
                    root
                    / "data"
                    / "warehouse"
                    / "current"
                    / "intelligence"
                    / "intelligence_recommendations.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
