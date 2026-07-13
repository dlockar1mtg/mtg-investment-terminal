from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.portfolio.engine import build_portfolio_datasets
from terminal2.portfolio.exports import publish_portfolio_datasets
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class PortfolioPublicationTests(unittest.TestCase):
    def test_publication(self):
        universe = pd.DataFrame({
            "investment_product_id": ["p1"],
            "box_name": ["Alpha"],
            "set_name": ["A"],
            "product_type": ["Collector Booster Display"],
            "current_price": [100.0],
            "investment_score": [80.0],
            "risk_adjusted_score": [78.0],
            "market_intelligence_score": [75.0],
            "market_intelligence_confidence": [70.0],
            "expected_cagr": [0.15],
            "projection_confidence": [80.0],
            "prob_loss": [0.15],
            "annualized_volatility": [0.20],
            "mc_median_5yr": [200.0],
            "buy_signal": ["Buy"],
        })
        holdings = pd.DataFrame({
            "investment_product_id": ["p1"],
            "quantity": [1.0],
            "acquisition_cost_total": [90.0],
            "acquisition_date": ["2025-01-01"],
            "notes": [""],
        })

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            result = build_portfolio_datasets(
                universe, holdings
            )
            published = publish_portfolio_datasets(
                result.datasets,
                warehouse=warehouse,
            )

            self.assertEqual(len(published), 7)
            self.assertTrue(
                (
                    root
                    / "data"
                    / "warehouse"
                    / "current"
                    / "portfolio"
                    / "portfolio_positions.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
