from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.registry import (
    REGISTRY_COLUMNS,
    build_secret_lair_datasets,
)


class SecretLairRegistryTests(unittest.TestCase):
    def test_empty_registry_builds_all_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.csv"
            pd.DataFrame(
                columns=REGISTRY_COLUMNS
            ).to_csv(path, index=False)

            result = build_secret_lair_datasets(
                registry_path=path
            )
            self.assertEqual(len(result.datasets), 7)
            self.assertEqual(
                len(result.datasets["secret_lair_summary"]),
                1,
            )
            self.assertFalse(
                result.datasets[
                    "secret_lair_data_quality"
                ].empty
            )

    def test_registry_builds_catalogs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.csv"
            row = {column: "" for column in REGISTRY_COLUMNS}
            row.update({
                "secret_lair_id": "SLTEST0001",
                "drop_name": "Example Drop",
                "variant_name": "Foil",
                "finish": "foil",
                "product_family": "drop",
                "release_date": "2026-01-15",
                "sale_start_date": "2026-01-01",
                "sale_end_date": "2026-01-07",
                "msrp_usd": 39.99,
                "currency": "USD",
                "franchise": "Magic",
                "ip_category": "Magic",
                "universes_beyond": False,
                "artist_names": "Artist One|Artist Two",
                "card_count": 5,
                "event_type": "standalone",
                "availability_model": "limited quantity",
                "status": "released",
            })
            pd.DataFrame([row]).to_csv(path, index=False)

            datasets = build_secret_lair_datasets(
                registry_path=path
            ).datasets
            self.assertEqual(
                len(datasets["secret_lair_registry"]),
                1,
            )
            self.assertEqual(
                len(datasets["secret_lair_artist_catalog"]),
                2,
            )
            self.assertEqual(
                len(datasets["secret_lair_ip_catalog"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
