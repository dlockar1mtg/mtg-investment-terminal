import unittest

import pandas as pd

from terminal2.return_analytics.engine import (
    _asset_class_summary,
    _product_metrics,
    _rankings,
    _rolling_and_drawdowns,
)


class UniversalReturnAnalyticsEngineTests(unittest.TestCase):
    def canonical(self):
        rows = []
        for asset_class, product_id, product_name, growth in (
            ("Booster Product", "BOX-1", "Test Booster", 1.02),
            ("Secret Lair", "SL-1", "Test Secret Lair", 1.03),
        ):
            for index, date in enumerate(
                pd.date_range("2024-01-01", periods=25, freq="MS")
            ):
                rows.append(
                    {
                        "price_month": date,
                        "investment_product_id": product_id,
                        "asset_class": asset_class,
                        "product_name": product_name,
                        "market_price": 100 * growth ** index,
                        "source_count": 1,
                        "source_name": "test",
                    }
                )
        return pd.DataFrame(rows)

    def test_both_asset_classes_are_analyzed(self):
        canonical = self.canonical()
        rolling, drawdowns = _rolling_and_drawdowns(canonical)
        summary, risk, momentum, coverage = _product_metrics(
            canonical, rolling, drawdowns
        )
        self.assertEqual(set(summary["asset_class"]), {
            "Booster Product",
            "Secret Lair",
        })
        self.assertTrue(summary["analytics_status"].eq("Ready").all())
        self.assertTrue(coverage["rolling_24m_available"].all())

        rankings = _rankings(summary, risk, momentum)
        self.assertTrue(rankings["composite_rank"].notna().all())
        self.assertTrue(rankings["asset_class_rank"].notna().all())

        asset_summary = _asset_class_summary(summary, coverage)
        self.assertEqual(len(asset_summary), 2)

    def test_drawdown_never_positive(self):
        canonical = self.canonical()
        canonical.loc[
            (canonical["investment_product_id"].eq("SL-1"))
            & (canonical.groupby("investment_product_id").cumcount().eq(10)),
            "market_price",
        ] = 50
        rolling, drawdowns = _rolling_and_drawdowns(canonical)
        self.assertTrue((drawdowns["drawdown"] <= 0).all())


if __name__ == "__main__":
    unittest.main()
