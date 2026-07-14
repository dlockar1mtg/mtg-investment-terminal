from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from terminal2.calibration import engine


class CalibrationEngineTests(unittest.TestCase):
    def _vintages(self):
        return pd.DataFrame(
            [
                {
                    "forecast_run_id": "R1",
                    "forecast_as_of_date": "2025-01-01",
                    "forecast_created_at_utc": "2025-01-01T00:00:00+00:00",
                    "investment_product_id": "P1",
                    "box_name": "Product One",
                    "set_name": "Set",
                    "product_type": "Collector Booster Display",
                    "horizon_months": 6,
                    "target_date": "2025-07-01",
                    "current_price": 100.0,
                    "forecast_price": 120.0,
                    "forecast_expected_return": 0.20,
                    "forecast_expected_cagr": 0.44,
                    "probability_of_loss": 0.20,
                    "forecast_confidence": 80.0,
                    "conviction_score": 75.0,
                    "recommendation": "Buy",
                    "recommendation_score": 70.0,
                    "overall_confidence_score": 78.0,
                    "overall_risk_score": 35.0,
                    "model_version": "2.9.0",
                },
                {
                    "forecast_run_id": "R1",
                    "forecast_as_of_date": "2025-01-01",
                    "forecast_created_at_utc": "2025-01-01T00:00:00+00:00",
                    "investment_product_id": "P2",
                    "box_name": "Product Two",
                    "set_name": "Set",
                    "product_type": "Draft Booster Box",
                    "horizon_months": 6,
                    "target_date": "2025-07-01",
                    "current_price": 100.0,
                    "forecast_price": 90.0,
                    "forecast_expected_return": -0.10,
                    "forecast_expected_cagr": -0.19,
                    "probability_of_loss": 0.70,
                    "forecast_confidence": 70.0,
                    "conviction_score": 35.0,
                    "recommendation": "Avoid",
                    "recommendation_score": 25.0,
                    "overall_confidence_score": 68.0,
                    "overall_risk_score": 70.0,
                    "model_version": "2.9.0",
                },
            ]
        )

    def _prices(self):
        return pd.DataFrame(
            [
                {
                    "investment_product_id": "P1",
                    "observation_date": pd.Timestamp(
                        "2025-07-05"
                    ),
                    "market_price": 115.0,
                },
                {
                    "investment_product_id": "P2",
                    "observation_date": pd.Timestamp(
                        "2025-07-03"
                    ),
                    "market_price": 85.0,
                },
            ]
        )

    def test_matches_matured_outcomes(self):
        outcomes = engine._match_realized_outcomes(
            self._vintages(),
            self._prices(),
            evaluation_date="2025-08-01",
        )
        self.assertEqual(
            int(
                outcomes[
                    "maturity_status"
                ].eq("matured").sum()
            ),
            2,
        )

    def test_calculates_errors_and_recommendation_success(self):
        vintages = self._vintages()
        outcomes = engine._match_realized_outcomes(
            vintages,
            self._prices(),
            evaluation_date="2025-08-01",
        )
        errors = engine._forecast_errors(
            vintages,
            outcomes,
        )
        performance = (
            engine._recommendation_performance(
                vintages,
                outcomes,
            )
        )
        self.assertEqual(len(errors), 2)
        self.assertTrue(
            errors["direction_correct"].all()
        )
        self.assertTrue(
            performance[
                "recommendation_success"
            ].all()
        )

    def test_first_run_is_valid_without_matured_forecasts(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "vintages.csv"
            with patch.object(
                engine,
                "VINTAGE_ARCHIVE_PATH",
                archive,
            ), patch.object(
                engine,
                "_build_current_vintage",
                return_value=self._vintages().assign(
                    forecast_as_of_date="2026-07-14",
                    target_date="2027-01-14",
                ),
            ), patch.object(
                engine,
                "_load_historical_prices",
                return_value=self._prices(),
            ):
                result = (
                    engine.build_model_calibration_datasets(
                        evaluation_date="2026-07-14"
                    )
                )
            self.assertEqual(
                len(result.datasets),
                8,
            )
            summary = result.datasets[
                "calibration_executive_summary"
            ].iloc[0]
            self.assertEqual(
                summary["matured_forecast_count"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
