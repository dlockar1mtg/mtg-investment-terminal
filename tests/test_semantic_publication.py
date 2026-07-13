from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.semantic.contracts import SEMANTIC_DATASET_CONTRACTS
from terminal2.semantic.exports import publish_semantic_datasets
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class SemanticPublicationTests(unittest.TestCase):
    def test_publication(self):
        datasets = {}
        for name, contract in SEMANTIC_DATASET_CONTRACTS.items():
            row = {
                column: f"{column}_value"
                for column in contract.required_columns
            }
            for column in (
                "DateKey",
                "SnapshotDateKey",
                "horizon_months",
                "RowCount",
            ):
                if column in row:
                    row[column] = 20260713
            for column in (
                "current_price",
                "investment_score",
                "risk_adjusted_score",
                "conviction_score",
                "market_price",
                "base_forecast_price",
                "bear_forecast_price",
                "bull_forecast_price",
                "expected_return",
                "probability_of_loss",
                "quantity",
                "current_value",
                "portfolio_weight",
                "KPIValue",
            ):
                if column in row:
                    row[column] = 1.0
            datasets[name] = pd.DataFrame([row])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            published = publish_semantic_datasets(
                datasets,
                warehouse=warehouse,
            )

            self.assertEqual(len(published), 11)
            self.assertTrue(
                (
                    root
                    / "data"
                    / "warehouse"
                    / "current"
                    / "semantic"
                    / "semantic_dim_product.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
