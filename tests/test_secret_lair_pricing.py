from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.secret_lair.pricing import (
    PRICE_COLUMNS,
    build_secret_lair_pricing_datasets,
)
from terminal2.secret_lair.registry import REGISTRY_COLUMNS


class SecretLairPricingTests(unittest.TestCase):
    def _registry(self, path):
        row = {
            column: ""
            for column in REGISTRY_COLUMNS
        }
        row.update({
            "secret_lair_id": "SLTEST0001",
            "drop_name": "Example Drop",
            "variant_name": "Foil",
            "finish": "foil",
            "product_family": "drop",
            "release_date": "2025-01-01",
            "msrp_usd": 39.99,
            "currency": "USD",
            "franchise": "Magic",
            "status": "released",
        })
        pd.DataFrame([row]).to_csv(path, index=False)

    def test_empty_history_builds_all_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry.csv"
            prices = root / "prices.csv"
            self._registry(registry)
            pd.DataFrame(
                columns=PRICE_COLUMNS
            ).to_csv(prices, index=False)

            datasets = build_secret_lair_pricing_datasets(
                registry_path=registry,
                price_path=prices,
            ).datasets
            self.assertEqual(len(datasets), 7)
            self.assertEqual(
                len(datasets["secret_lair_market_summary"]),
                1,
            )

    def test_pricing_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = root / "registry.csv"
            prices = root / "prices.csv"
            self._registry(registry)
            pd.DataFrame([
                {
                    "observation_date": "2025-01-31",
                    "secret_lair_id": "SLTEST0001",
                    "source_name": "tcgplayer",
                    "market_price": 50.0,
                    "currency": "USD",
                },
                {
                    "observation_date": "2026-01-31",
                    "secret_lair_id": "SLTEST0001",
                    "source_name": "tcgplayer",
                    "market_price": 75.0,
                    "currency": "USD",
                },
            ]).to_csv(prices, index=False)

            datasets = build_secret_lair_pricing_datasets(
                registry_path=registry,
                price_path=prices,
            ).datasets
            current = datasets[
                "secret_lair_current_prices"
            ].iloc[0]
            returns = datasets[
                "secret_lair_returns"
            ].iloc[0]

            self.assertEqual(current["market_price"], 75.0)
            self.assertGreater(
                current["premium_to_msrp_pct"],
                0,
            )
            self.assertAlmostEqual(
                returns["return_365d"],
                0.5,
                places=2,
            )


if __name__ == "__main__":
    unittest.main()
