from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.warehouse_core import (
    Warehouse,
    get_warehouse_config,
)
from terminal2.warehouse_migration import (
    WarehouseMigration,
    discover_legacy_datasets,
    validate_migration,
)


class WarehouseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        products = (
            self.root
            / "data"
            / "dashboard"
            / "products"
        )
        market = (
            self.root
            / "data"
            / "dashboard"
            / "market"
        )
        analytics = (
            self.root
            / "data"
            / "analytics"
            / "current"
        )

        products.mkdir(parents=True)
        market.mkdir(parents=True)
        analytics.mkdir(parents=True)

        pd.DataFrame(
            {
                "investment_product_id": ["p1", "p2"],
                "score": [90.0, 80.0],
            }
        ).to_csv(
            products / "product_rankings.csv",
            index=False,
        )

        pd.DataFrame(
            {
                "snapshot_date": ["2026-07-12"],
                "health_score": [72.5],
            }
        ).to_csv(
            market / "market_health.csv",
            index=False,
        )

        pd.DataFrame(
            {
                "investment_product_id": ["p1"],
                "market_intelligence_score": [88.0],
            }
        ).to_csv(
            analytics / "market_intelligence.csv",
            index=False,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog(self):
        candidates, warnings = discover_legacy_datasets(
            self.root
        )
        names = {
            candidate.dataset_name
            for candidate in candidates
        }

        self.assertIn("product_rankings", names)
        self.assertIn("market_health", names)
        self.assertIn(
            "current_market_intelligence",
            names,
        )
        self.assertEqual(warnings, [])

    def test_migration(self):
        warehouse = Warehouse(
            config=get_warehouse_config(self.root)
        )
        result = WarehouseMigration(
            warehouse=warehouse
        ).migrate()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["datasets_migrated"], 3)
        self.assertTrue(
            (
                self.root
                / "data"
                / "warehouse"
                / "current"
                / "products"
                / "product_rankings.csv"
            ).exists()
        )
        self.assertTrue(
            validate_migration(
                project_root=self.root
            ).passed
        )


if __name__ == "__main__":
    unittest.main()
