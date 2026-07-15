from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from terminal2.secret_lair.archive import engine
from terminal2.secret_lair.pricing import PRICE_COLUMNS


class SecretLairArchiveRegistryIntegrityTests(unittest.TestCase):
    def test_master_only_products_are_not_import_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            product_map = pd.DataFrame([
                {
                    "secret_lair_id": "SL-PROD",
                    "tcgplayer_product_id": "1",
                    "tcgcsv_category_id": "1",
                    "tcgcsv_group_id": "1",
                    "product_name": "Production Product",
                },
                {
                    "secret_lair_id": "SL-MASTER-ONLY",
                    "tcgplayer_product_id": "2",
                    "tcgcsv_category_id": "1",
                    "tcgcsv_group_id": "1",
                    "product_name": "Master Only Product",
                },
            ])
            raw = pd.DataFrame([
                {
                    "observation_date": "2024-02-08",
                    "secret_lair_id": "SL-PROD",
                    "source_name": "tcgcsv_archive",
                    "market_price": 50.0,
                    "low_price": 45.0,
                    "price_data_quality": 90,
                },
                {
                    "observation_date": "2024-02-08",
                    "secret_lair_id": "SL-MASTER-ONLY",
                    "source_name": "tcgcsv_archive",
                    "market_price": 60.0,
                    "low_price": 55.0,
                    "price_data_quality": 90,
                },
            ])
            registry = pd.DataFrame([
                {"secret_lair_id": "SL-PROD"}
            ])
            product_map_path = root / "product_map.csv"
            raw_path = root / "raw.csv"
            log_path = root / "log.csv"
            product_map.to_csv(product_map_path, index=False)
            raw.to_csv(raw_path, index=False)

            with patch.object(engine, "PRODUCT_MAP_PATH", product_map_path),                  patch.object(engine, "RAW_PATH", raw_path),                  patch.object(engine, "LOG_PATH", log_path),                  patch.object(engine, "ROOT", root),                  patch.object(engine, "load_secret_lair_registry", return_value=(registry, True)):
                result = engine.build_secret_lair_archive(download=False)

            candidates = result.import_candidates.set_index("secret_lair_id")
            self.assertTrue(bool(candidates.loc["SL-PROD", "import_eligible"]))
            self.assertFalse(bool(candidates.loc["SL-MASTER-ONLY", "import_eligible"]))
            self.assertIn(
                "not present in the production registry",
                candidates.loc["SL-MASTER-ONLY", "import_reason"],
            )

    def test_apply_removes_existing_orphan_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            price_path = root / "prices.csv"
            backup_root = root / "backups"

            existing = pd.DataFrame([
                {
                    "observation_date": "2024-02-08",
                    "secret_lair_id": "SL-PROD",
                    "source_name": "tcgcsv_archive",
                    "market_price": 50.0,
                },
                {
                    "observation_date": "2024-02-08",
                    "secret_lair_id": "SL-ORPHAN",
                    "source_name": "tcgcsv_archive",
                    "market_price": 70.0,
                },
            ])
            for column in PRICE_COLUMNS:
                if column not in existing:
                    existing[column] = pd.NA
            existing[list(PRICE_COLUMNS)].to_csv(price_path, index=False)

            candidates = pd.DataFrame([
                {
                    "observation_date": "2024-03-01",
                    "secret_lair_id": "SL-PROD",
                    "source_name": "tcgcsv_archive",
                    "market_price": 55.0,
                    "low_price": 50.0,
                    "price_data_quality": 90,
                    "import_eligible": True,
                    "import_reason": "Valid",
                }
            ])
            result = engine.ArchiveBuildResult(
                datasets={},
                raw_prices=pd.DataFrame(),
                import_candidates=candidates,
                apply_ready=True,
            )
            registry = pd.DataFrame([{"secret_lair_id": "SL-PROD"}])

            with patch.object(engine, "PRICE_PATH", price_path),                  patch.object(engine, "BACKUP_ROOT", backup_root),                  patch.object(engine, "load_secret_lair_registry", return_value=(registry, True)):
                added, total, removed = engine.apply_archive_to_production(result)

            repaired = pd.read_csv(price_path)
            self.assertEqual(added, 1)
            self.assertEqual(removed, 1)
            self.assertEqual(total, 2)
            self.assertNotIn("SL-ORPHAN", set(repaired["secret_lair_id"]))
            self.assertTrue(any(backup_root.iterdir()))


if __name__ == "__main__":
    unittest.main()
