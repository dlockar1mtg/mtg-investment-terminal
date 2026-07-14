from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.backfill.engine import (
    build_secret_lair_backfill,
)
from terminal2.secret_lair.backfill.exports import (
    publish_secret_lair_backfill_datasets,
)
from terminal2.secret_lair.backfill.sources import (
    CATALOG_COLUMNS,
    OVERRIDE_COLUMNS,
    SOURCE_PRICE_COLUMNS,
)
from terminal2.secret_lair.pricing import PRICE_COLUMNS
from terminal2.secret_lair.registry import REGISTRY_COLUMNS
from terminal2.warehouse_core import (
    Warehouse,
    get_warehouse_config,
)


class SecretLairBackfillPublicationTests(unittest.TestCase):
    def test_empty_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {
                "registry": root / "registry.csv",
                "prices": root / "prices.csv",
                "catalog": root / "catalog.csv",
                "source_prices": root / "source_prices.csv",
                "overrides": root / "overrides.csv",
            }
            pd.DataFrame(
                columns=REGISTRY_COLUMNS
            ).to_csv(paths["registry"], index=False)
            pd.DataFrame(
                columns=PRICE_COLUMNS
            ).to_csv(paths["prices"], index=False)
            pd.DataFrame(
                columns=CATALOG_COLUMNS
            ).to_csv(paths["catalog"], index=False)
            pd.DataFrame(
                columns=SOURCE_PRICE_COLUMNS
            ).to_csv(paths["source_prices"], index=False)
            pd.DataFrame(
                columns=OVERRIDE_COLUMNS
            ).to_csv(paths["overrides"], index=False)

            datasets = build_secret_lair_backfill(
                registry_path=paths["registry"],
                price_path=paths["prices"],
                source_catalog_path=paths["catalog"],
                source_prices_path=paths["source_prices"],
                overrides_path=paths["overrides"],
            ).datasets
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            published = (
                publish_secret_lair_backfill_datasets(
                    datasets,
                    warehouse=warehouse,
                )
            )
            self.assertEqual(len(published), 7)


if __name__ == "__main__":
    unittest.main()
