from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.backfill.engine import (
    apply_secret_lair_backfill,
    build_secret_lair_backfill,
)
from terminal2.secret_lair.backfill.sources import (
    CATALOG_COLUMNS,
    OVERRIDE_COLUMNS,
    SOURCE_PRICE_COLUMNS,
)
from terminal2.secret_lair.pricing import PRICE_COLUMNS
from terminal2.secret_lair.registry import REGISTRY_COLUMNS


class SecretLairBackfillEngineTests(unittest.TestCase):
    def test_build_and_apply_new_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry.csv"
            prices = root / "prices.csv"
            catalog = root / "catalog.csv"
            source_prices = root / "source_prices.csv"
            overrides = root / "overrides.csv"
            log = root / "apply_log.csv"

            pd.DataFrame(
                columns=REGISTRY_COLUMNS
            ).to_csv(registry, index=False)
            pd.DataFrame(
                columns=PRICE_COLUMNS
            ).to_csv(prices, index=False)

            catalog_row = {
                column: ""
                for column in CATALOG_COLUMNS
            }
            catalog_row.update({
                "source_name": "source_a",
                "source_record_id": "100",
                "drop_name": "Example Drop",
                "variant_name": "Foil Edition",
                "finish": "foil",
                "product_family": "drop",
                "release_date": "2025-01-01",
                "msrp_usd": 39.99,
                "currency": "USD",
                "franchise": "Magic",
                "status": "released",
            })
            pd.DataFrame([catalog_row]).to_csv(
                catalog,
                index=False,
            )

            price_row = {
                column: ""
                for column in SOURCE_PRICE_COLUMNS
            }
            price_row.update({
                "source_name": "source_a",
                "source_record_id": "100",
                "observation_date": "2026-01-01",
                "market_price": 75.0,
                "currency": "USD",
            })
            pd.DataFrame([price_row]).to_csv(
                source_prices,
                index=False,
            )
            pd.DataFrame(
                columns=OVERRIDE_COLUMNS
            ).to_csv(overrides, index=False)

            result = build_secret_lair_backfill(
                registry_path=registry,
                price_path=prices,
                source_catalog_path=catalog,
                source_prices_path=source_prices,
                overrides_path=overrides,
            )
            summary = result.datasets[
                "secret_lair_backfill_summary"
            ].iloc[0]
            self.assertTrue(summary["apply_ready"])
            self.assertEqual(summary["new_asset_rows"], 1)
            self.assertEqual(
                len(
                    result.datasets[
                        "secret_lair_backfill_prices"
                    ]
                ),
                1,
            )

            applied = apply_secret_lair_backfill(
                result,
                registry_path=registry,
                price_path=prices,
                apply_log_path=log,
            )
            self.assertEqual(
                applied.registry_rows_written,
                1,
            )
            self.assertEqual(
                applied.price_rows_written,
                1,
            )


if __name__ == "__main__":
    unittest.main()
