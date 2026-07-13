from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.semantic.engine import build_semantic_datasets
from terminal2.warehouse_core import get_warehouse_config


class SemanticEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        config = get_warehouse_config(self.root)

        def save(category, name, frame):
            path = config.current_root / category / f"{name}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index=False)

        save("products", "historical_prices", pd.DataFrame({
            "observation_date": ["2026-01-01", "2026-02-01"],
            "investment_product_id": ["p1", "p1"],
            "price_source": ["tcgcsv", "tcgcsv"],
            "market_price": [100.0, 110.0],
            "box_name": ["Alpha", "Alpha"],
            "set_name": ["Set A", "Set A"],
            "product_type": [
                "Collector Booster Display",
                "Collector Booster Display",
            ],
        }))
        save("intelligence", "forecast_product_summary", pd.DataFrame({
            "investment_product_id": ["p1"],
            "box_name": ["Alpha"],
            "set_name": ["Set A"],
            "product_type": ["Collector Booster Display"],
            "current_price": [110.0],
            "investment_score": [80.0],
            "risk_adjusted_score": [75.0],
            "conviction_score": [78.0],
            "forecast_confidence": [72.0],
            "forecast_regime": ["Bull"],
            "conviction_tier": ["High"],
        }))
        save("intelligence", "forecast_horizons", pd.DataFrame({
            "investment_product_id": ["p1"],
            "horizon_months": [12],
            "base_forecast_price": [130.0],
            "bear_forecast_price": [90.0],
            "bull_forecast_price": [170.0],
            "expected_return": [0.1818],
            "probability_of_loss": [0.20],
        }))
        save("market", "market_intelligence", pd.DataFrame({
            "investment_product_id": ["p1"],
            "market_intelligence_score": [75.0],
            "market_intelligence_confidence": [70.0],
        }))
        save("metadata", "historical_coverage", pd.DataFrame({
            "investment_product_id": ["p1"],
            "observation_count": [2],
            "history_confidence": [50.0],
        }))
        save("portfolio", "portfolio_recommendations", pd.DataFrame({
            "investment_product_id": ["p1"],
            "recommendation": ["Candidate Buy"],
            "target_weight": [0.10],
            "current_portfolio_weight": [0.0],
        }))
        save("portfolio", "portfolio_positions", pd.DataFrame(columns=[
            "investment_product_id",
            "quantity",
            "current_price",
            "current_value",
            "portfolio_weight",
        ]))
        save("executive", "forecast_market_summary", pd.DataFrame({
            "average_conviction_score": [78.0],
            "average_forecast_confidence": [72.0],
            "bullish_product_count": [1],
            "bearish_product_count": [0],
        }))
        save("executive", "portfolio_summary", pd.DataFrame({
            "current_value": [0.0],
            "portfolio_health_score": [0.0],
        }))
        save("executive", "historical_summary", pd.DataFrame({
            "observation_count": [2],
            "product_count": [1],
        }))
        save("executive", "market_health_summary", pd.DataFrame({
            "market_health_score": [70.0],
        }))

        config.manifests_root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{
            "dataset_name": "historical_prices",
            "category": "products",
            "published_at_utc": "2026-07-13T00:00:00+00:00",
            "row_count": 2,
            "status": "success",
            "current_path": "example.csv",
            "refresh_id": "test",
        }]).to_csv(
            config.manifests_root / "dataset_manifest.csv",
            index=False,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_semantic_star_schema(self):
        result = build_semantic_datasets(
            project_root=self.root
        )
        datasets = result.datasets

        self.assertEqual(len(datasets), 11)
        self.assertEqual(
            len(datasets["semantic_dim_product"]),
            1,
        )
        self.assertEqual(
            len(datasets["semantic_fact_price_history"]),
            2,
        )
        self.assertEqual(
            len(datasets["semantic_fact_forecast"]),
            1,
        )
        self.assertEqual(
            len(datasets["semantic_executive_kpis"]),
            12,
        )
        product_key = datasets[
            "semantic_dim_product"
        ].iloc[0]["ProductKey"]
        self.assertTrue(product_key.startswith("P_"))


if __name__ == "__main__":
    unittest.main()
