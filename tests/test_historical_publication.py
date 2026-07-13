from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.history.exports import publish_historical_datasets
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class HistoricalPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.warehouse = Warehouse(
            config=get_warehouse_config(self.root)
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_standardized_historical_publication(self):
        datasets = {
            "historical_prices": pd.DataFrame({
                "observation_date": ["2026-07-01"],
                "investment_product_id": ["p1"],
                "price_source": ["tcgcsv"],
                "market_price": [100.0],
            }),
            "monthly_price_history": pd.DataFrame({
                "year_month": ["2026-07"],
                "observation_date": ["2026-07-01"],
                "investment_product_id": ["p1"],
                "price_source": ["tcgcsv"],
                "market_price": [100.0],
            }),
            "historical_returns": pd.DataFrame({
                "year_month": ["2026-07"],
                "investment_product_id": ["p1"],
                "price_source": ["tcgcsv"],
                "market_price": [100.0],
                "monthly_return": [0.10],
            }),
            "historical_price_features": pd.DataFrame({
                "investment_product_id": ["p1"],
                "latest_price": [100.0],
                "observation_count": [12],
                "first_observation_date": ["2025-08-01"],
                "latest_observation_date": ["2026-07-01"],
                "history_confidence": [100.0],
            }),
            "historical_coverage": pd.DataFrame({
                "investment_product_id": ["p1"],
                "observation_count": [12],
                "first_observation_date": ["2025-08-01"],
                "latest_observation_date": ["2026-07-01"],
                "history_span_days": [334],
                "source_count": [1],
                "coverage_status": ["Moderate"],
            }),
            "historical_source_quality": pd.DataFrame({
                "price_source": ["tcgcsv"],
                "observation_count": [12],
                "product_count": [1],
                "first_observation_date": ["2025-08-01"],
                "latest_observation_date": ["2026-07-01"],
                "average_price_data_quality": [90.0],
            }),
            "historical_summary": pd.DataFrame({
                "snapshot_date": ["2026-07-13"],
                "observation_count": [12],
                "product_count": [1],
                "source_count": [1],
                "first_observation_date": ["2025-08-01"],
                "latest_observation_date": ["2026-07-01"],
            }),
        }

        results = publish_historical_datasets(
            datasets,
            warehouse=self.warehouse,
        )

        self.assertEqual(len(results), 7)
        self.assertTrue(
            (
                self.root
                / "data"
                / "warehouse"
                / "current"
                / "products"
                / "historical_prices.csv"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
