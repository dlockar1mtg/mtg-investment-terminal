from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.price_imports import (
    import_secret_lair_prices,
)
from terminal2.secret_lair.registry import REGISTRY_COLUMNS


class SecretLairPriceImportTests(unittest.TestCase):
    def test_import_validates_registry_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry.csv"
            source = root / "prices.csv"
            output = root / "normalized.csv"

            row = {
                column: ""
                for column in REGISTRY_COLUMNS
            }
            row.update({
                "secret_lair_id": "SLTEST0001",
                "drop_name": "Example",
                "variant_name": "Foil",
                "finish": "foil",
            })
            pd.DataFrame([row]).to_csv(
                registry,
                index=False,
            )
            pd.DataFrame([{
                "observation_date": "2026-01-31",
                "secret_lair_id": "SLTEST0001",
                "source_name": "TCGPlayer",
                "market_price": "55.00",
                "currency": "usd",
            }]).to_csv(source, index=False)

            result = import_secret_lair_prices(
                source,
                output_path=output,
                registry_path=registry,
            )
            imported = pd.read_csv(output)

            self.assertEqual(result.imported_rows, 1)
            self.assertEqual(result.rejected_rows, 0)
            self.assertEqual(
                imported.iloc[0]["source_name"],
                "tcgplayer",
            )


if __name__ == "__main__":
    unittest.main()
