import unittest

import pandas as pd

from terminal2.secret_lair.pricing import _current_prices, _returns


class SecretLairPricingTimezoneTests(unittest.TestCase):
    def test_returns_accept_timezone_aware_release_date(self):
        enriched = pd.DataFrame(
            [
                {
                    "observation_date": "2026-07-14",
                    "secret_lair_id": "SL-TEST-1",
                    "source_name": "tcgcsv",
                    "market_price": 100.0,
                    "low_price": 90.0,
                    "listing_count": 10,
                    "sales_count_30d": 2,
                    "currency": "USD",
                    "source_url": "",
                    "source_record_id": "1",
                    "price_data_quality": 90,
                    "notes": "",
                    "drop_name": "Timezone Test",
                    "variant_name": "Foil Edition",
                    "finish": "foil",
                    "release_date": "2021-03-01T08:00:00Z",
                    "msrp_usd": 39.99,
                },
                {
                    "observation_date": "2025-07-14",
                    "secret_lair_id": "SL-TEST-1",
                    "source_name": "tcgcsv",
                    "market_price": 80.0,
                    "low_price": 75.0,
                    "listing_count": 8,
                    "sales_count_30d": 1,
                    "currency": "USD",
                    "source_url": "",
                    "source_record_id": "2",
                    "price_data_quality": 90,
                    "notes": "",
                    "drop_name": "Timezone Test",
                    "variant_name": "Foil Edition",
                    "finish": "foil",
                    "release_date": "2021-03-01T08:00:00Z",
                    "msrp_usd": 39.99,
                },
            ]
        )

        current = _current_prices(enriched)
        result = _returns(enriched, current)

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result.iloc[0]["secret_lair_id"],
            "SL-TEST-1",
        )
        self.assertGreater(
            float(result.iloc[0]["annualized_return"]),
            0,
        )


if __name__ == "__main__":
    unittest.main()
