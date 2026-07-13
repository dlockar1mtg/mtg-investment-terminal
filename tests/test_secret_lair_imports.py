from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.imports import (
    import_secret_lair_registry,
)


class SecretLairImportTests(unittest.TestCase):
    def test_import_normalizes_and_generates_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.csv"
            output = root / "registry.csv"
            pd.DataFrame([{
                "drop_name": "Example Drop",
                "variant_name": "Foil Edition",
                "finish": "Foil",
                "product_family": "Drop",
                "release_date": "2026-01-15",
                "msrp_usd": "39.99",
                "franchise": "Magic",
                "ip_category": "Magic",
                "universes_beyond": "No",
                "artist_names": "Artist One|Artist Two",
                "event_type": "Standalone",
                "availability_model": "Limited Quantity",
                "status": "Released",
            }]).to_csv(source, index=False)

            result = import_secret_lair_registry(
                source,
                output_path=output,
            )
            imported = pd.read_csv(output)

            self.assertEqual(result.imported_rows, 1)
            self.assertEqual(result.rejected_rows, 0)
            self.assertTrue(
                imported.iloc[0]["secret_lair_id"].startswith(
                    "SL"
                )
            )
            self.assertEqual(
                imported.iloc[0]["finish"],
                "foil",
            )


if __name__ == "__main__":
    unittest.main()
