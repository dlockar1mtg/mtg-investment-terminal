import unittest
from unittest.mock import patch

import pandas as pd

from terminal2.calibration import engine


class CalibrationTargetDateTests(unittest.TestCase):
    def test_build_current_vintage_supports_all_horizons(self):
        horizons = pd.DataFrame(
            [
                {
                    "investment_product_id": "P1",
                    "box_name": "Example Product",
                    "horizon_months": months,
                    "current_price": 100.0,
                    "base_forecast_price": 110.0,
                    "expected_return": 0.10,
                    "probability_of_loss": 0.20,
                    "forecast_confidence": 75.0,
                }
                for months in (6, 12, 36, 60)
            ]
        )
        summary = pd.DataFrame(
            [
                {
                    "investment_product_id": "P1",
                    "set_name": "Example Set",
                    "product_type": "Collector Booster Display",
                    "forecast_expected_cagr": 0.10,
                    "conviction_score": 70.0,
                }
            ]
        )
        recommendations = pd.DataFrame(
            [
                {
                    "investment_product_id": "P1",
                    "recommendation": "Buy",
                    "recommendation_score": 70.0,
                    "overall_confidence_score": 75.0,
                    "overall_risk_score": 35.0,
                }
            ]
        )

        def fake_read_csv(path, columns=()):
            name = str(path)
            if name.endswith("forecast_horizons.csv"):
                return horizons.copy()
            if name.endswith("forecast_product_summary.csv"):
                return summary.copy()
            if name.endswith("intelligence_recommendations.csv"):
                return recommendations.copy()
            return pd.DataFrame(columns=list(columns))

        with patch.object(
            engine,
            "_read_csv",
            side_effect=fake_read_csv,
        ):
            result = engine._build_current_vintage(
                as_of_date="2026-07-14"
            )

        self.assertEqual(
            result["target_date"].tolist(),
            [
                "2027-01-14",
                "2027-07-14",
                "2029-07-14",
                "2031-07-14",
            ],
        )
        self.assertEqual(len(result), 4)


if __name__ == "__main__":
    unittest.main()
