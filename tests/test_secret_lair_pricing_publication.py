from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.pricing import (
    PRICE_COLUMNS,
    build_secret_lair_pricing_datasets,
)
from terminal2.secret_lair.pricing_exports import (
    publish_secret_lair_pricing_datasets,
)
from terminal2.secret_lair.registry import REGISTRY_COLUMNS
from terminal2.warehouse_core import (
    Warehouse,
    get_warehouse_config,
)


class SecretLairPricingPublicationTests(unittest.TestCase):
    def test_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry.csv"
            prices = root / "prices.csv"
            pd.DataFrame(
                columns=REGISTRY_COLUMNS
            ).to_csv(registry, index=False)
            pd.DataFrame(
                columns=PRICE_COLUMNS
            ).to_csv(prices, index=False)

            datasets = build_secret_lair_pricing_datasets(
                registry_path=registry,
                price_path=prices,
            ).datasets
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            published = (
                publish_secret_lair_pricing_datasets(
                    datasets,
                    warehouse=warehouse,
                )
            )

            self.assertEqual(len(published), 7)
            self.assertTrue(
                (
                    root
                    / "data"
                    / "warehouse"
                    / "current"
                    / "secret_lair"
                    / "secret_lair_current_prices.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
