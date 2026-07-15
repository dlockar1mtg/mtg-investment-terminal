from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.return_analytics.contracts import (
    RETURN_ANALYTICS_CONTRACTS,
)
from terminal2.return_analytics.exports import (
    publish_return_analytics_datasets,
)
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class UniversalReturnAnalyticsPublicationTests(unittest.TestCase):
    def test_empty_contract_publication(self):
        datasets = {
            name: pd.DataFrame(columns=contract.required_columns)
            for name, contract in RETURN_ANALYTICS_CONTRACTS.items()
        }
        datasets["universal_return_analytics_summary"] = pd.DataFrame(
            [
                {
                    "snapshot_date": "2026-07-15",
                    "product_count": 0,
                    "asset_class_count": 0,
                    "analytics_ready_count": 0,
                    "rolling_12m_ready_count": 0,
                    "rolling_24m_ready_count": 0,
                    "positive_cagr_count": 0,
                    "negative_cagr_count": 0,
                    "median_cagr": pd.NA,
                    "median_volatility": pd.NA,
                    "median_maximum_drawdown": pd.NA,
                    "analytics_status": "INSUFFICIENT_HISTORY",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            published = publish_return_analytics_datasets(
                datasets,
                warehouse=Warehouse(
                    config=get_warehouse_config(Path(temp))
                ),
            )
            self.assertEqual(
                len(published),
                len(RETURN_ANALYTICS_CONTRACTS),
            )


if __name__ == "__main__":
    unittest.main()
