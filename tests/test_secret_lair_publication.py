from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.exports import (
    publish_secret_lair_datasets,
)
from terminal2.secret_lair.registry import (
    REGISTRY_COLUMNS,
    build_secret_lair_datasets,
)
from terminal2.warehouse_core import (
    Warehouse,
    get_warehouse_config,
)


class SecretLairPublicationTests(unittest.TestCase):
    def test_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry_path = root / "registry.csv"
            pd.DataFrame(
                columns=REGISTRY_COLUMNS
            ).to_csv(registry_path, index=False)
            datasets = build_secret_lair_datasets(
                registry_path=registry_path
            ).datasets
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            published = publish_secret_lair_datasets(
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
                    / "secret_lair"
                    / "secret_lair_registry.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
