import unittest

import pandas as pd

from terminal2.secret_lair.backfill.matching import (
    match_source_catalog,
)
from terminal2.secret_lair.backfill.sources import (
    CATALOG_COLUMNS,
)


class SecretLairBackfillMatchingTests(unittest.TestCase):
    def _source(self):
        row = {column: "" for column in CATALOG_COLUMNS}
        row.update({
            "source_name": "source_a",
            "source_record_id": "100",
            "drop_name": "Example Drop",
            "variant_name": "Foil Edition",
            "finish": "foil",
            "release_date": "2025-01-01",
            "franchise": "Magic",
        })
        return pd.DataFrame([row])

    def test_exact_source_identity_match(self):
        registry = pd.DataFrame([{
            "secret_lair_id": "SLKNOWN",
            "source_name": "source_a",
            "source_record_id": "100",
            "drop_name": "Different Display Name",
            "variant_name": "Foil",
            "finish": "foil",
            "release_date": "2025-01-01",
            "franchise": "Magic",
        }])
        matches, review = match_source_catalog(
            self._source(),
            registry,
            pd.DataFrame(),
        )
        self.assertEqual(
            matches.iloc[0]["secret_lair_id"],
            "SLKNOWN",
        )
        self.assertEqual(
            matches.iloc[0]["match_method"],
            "exact_source_identity",
        )
        self.assertTrue(review.empty)

    def test_new_asset_gets_deterministic_id(self):
        matches, review = match_source_catalog(
            self._source(),
            pd.DataFrame(),
            pd.DataFrame(),
        )
        self.assertEqual(
            matches.iloc[0]["match_status"],
            "new_asset",
        )
        self.assertTrue(
            matches.iloc[0]["secret_lair_id"].startswith(
                "SL"
            )
        )
        self.assertTrue(review.empty)


if __name__ == "__main__":
    unittest.main()
