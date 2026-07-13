from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.market.exports import publish_module2_datasets
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class MarketPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.warehouse = Warehouse(
            config=get_warehouse_config(self.root)
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_standardized_market_publication(self):
        datasets = {
            "market_intelligence": pd.DataFrame({
                "investment_product_id": ["p1"],
                "market_intelligence_score": [80.0],
                "market_intelligence_confidence": [70.0],
            }),
            "market_signals": pd.DataFrame({
                "investment_product_id": ["p1"],
                "market_signal": ["Strong"],
                "signal_reason": ["Test"],
            }),
            "market_health": pd.DataFrame({
                "snapshot_date": ["2026-07-13"],
            }),
            "source_health": pd.DataFrame({
                "snapshot_date": ["2026-07-13"],
                "source_name": ["tcgcsv"],
                "source_health_score": [90.0],
                "status": ["Healthy"],
            }),
            "supply_metrics": pd.DataFrame({
                "observation_date": ["2026-07-13"],
                "investment_product_id": ["p1"],
                "source_name": ["manual"],
            }),
            "liquidity": pd.DataFrame({
                "observation_date": ["2026-07-13"],
                "investment_product_id": ["p1"],
                "source_name": ["manual"],
            }),
            "market_alerts": pd.DataFrame({
                "investment_product_id": ["p1"],
                "alert_type": ["MARKET_STRENGTH"],
                "severity": ["High"],
                "generated_at_utc": ["2026-07-13T00:00:00+00:00"],
            }),
            "market_health_summary": pd.DataFrame({
                "snapshot_date": ["2026-07-13"],
            }),
            "current_market_intelligence": pd.DataFrame({
                "investment_product_id": ["p1"],
                "market_intelligence_score": [80.0],
            }),
            "current_market_health": pd.DataFrame({
                "snapshot_date": ["2026-07-13"],
            }),
        }

        results = publish_module2_datasets(
            datasets,
            warehouse=self.warehouse,
        )

        self.assertEqual(len(results), 10)
        self.assertTrue(
            (
                self.root
                / "data"
                / "warehouse"
                / "current"
                / "market"
                / "market_intelligence.csv"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
