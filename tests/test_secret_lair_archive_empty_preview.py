import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal2.secret_lair.archive.contracts import ARCHIVE_CONTRACTS
from terminal2.secret_lair.archive.engine import build_secret_lair_archive
from terminal2.secret_lair.archive.exports import publish_archive_datasets
from terminal2.warehouse_core import Warehouse, get_warehouse_config


class SecretLairArchiveEmptyPreviewTests(unittest.TestCase):
    def test_empty_preview_publishes_all_contract_schemas(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch("terminal2.secret_lair.archive.engine.ROOT", root / "archive"), \
                 patch("terminal2.secret_lair.archive.engine.RAW_PATH", root / "archive" / "raw_prices.csv"), \
                 patch("terminal2.secret_lair.archive.engine.LOG_PATH", root / "archive" / "download_log.csv"), \
                 patch("terminal2.secret_lair.archive.engine.PRODUCT_MAP_PATH", root / "missing_product_map.csv"):
                result = build_secret_lair_archive(download=False)
                self.assertEqual(set(result.datasets), set(ARCHIVE_CONTRACTS))
                for name, contract in ARCHIVE_CONTRACTS.items():
                    self.assertTrue(set(contract.required_columns).issubset(result.datasets[name].columns))
                published = publish_archive_datasets(
                    result.datasets,
                    warehouse=Warehouse(config=get_warehouse_config(root)),
                )
                self.assertEqual(len(published), len(ARCHIVE_CONTRACTS))


if __name__ == "__main__":
    unittest.main()
