import unittest

import pandas as pd

from terminal2.intelligence.engine import (
    build_core_intelligence_datasets,
)


class CoreIntelligenceEngineTests(unittest.TestCase):
    def _universe(self):
        return pd.DataFrame(
            [
                {
                    "investment_product_id": "P1",
                    "box_name": "High Conviction Product",
                    "set_name": "Set A",
                    "product_type": "Collector Booster Display",
                    "current_price": 500.0,
                    "investment_score": 82.0,
                    "risk_adjusted_score": 80.0,
                    "expected_cagr": 0.18,
                    "projection_confidence": 90.0,
                    "prob_loss": 0.15,
                    "observation_count": 30,
                    "return_30d": 0.05,
                    "return_90d": 0.12,
                    "return_180d": 0.20,
                    "return_365d": 0.35,
                    "annualized_volatility": 0.20,
                    "trend_score": 80.0,
                    "history_confidence": 90.0,
                    "market_intelligence_score": 82.0,
                    "market_intelligence_confidence": 88.0,
                    "supply_signal_score": 80.0,
                    "sales_velocity_score": 75.0,
                    "liquidity_score": 85.0,
                },
                {
                    "investment_product_id": "P2",
                    "box_name": "Weak Evidence Product",
                    "set_name": "Set B",
                    "product_type": "Draft Booster Box",
                    "current_price": 100.0,
                    "investment_score": 40.0,
                    "risk_adjusted_score": 35.0,
                    "expected_cagr": 0.02,
                    "projection_confidence": 20.0,
                    "prob_loss": 0.55,
                    "observation_count": 2,
                    "return_30d": -0.05,
                    "return_90d": -0.10,
                    "return_180d": -0.15,
                    "return_365d": -0.20,
                    "annualized_volatility": 0.80,
                    "trend_score": 25.0,
                    "history_confidence": 20.0,
                    "market_intelligence_score": 35.0,
                    "market_intelligence_confidence": 25.0,
                    "supply_signal_score": 30.0,
                    "sales_velocity_score": 25.0,
                    "liquidity_score": 25.0,
                },
            ]
        )

    def test_builds_all_phase_one_datasets(self):
        result = build_core_intelligence_datasets(
            self._universe()
        )
        self.assertEqual(len(result.datasets), 7)
        recommendations = result.datasets[
            "intelligence_recommendations"
        ]
        self.assertEqual(len(recommendations), 2)
        self.assertTrue(
            recommendations[
                "overall_risk_score"
            ].between(0, 100).all()
        )
        self.assertTrue(
            recommendations[
                "overall_confidence_score"
            ].between(0, 100).all()
        )

    def test_stronger_product_ranks_better(self):
        result = build_core_intelligence_datasets(
            self._universe()
        )
        recommendations = (
            result.datasets[
                "intelligence_recommendations"
            ]
            .set_index("investment_product_id")
        )
        self.assertGreater(
            recommendations.loc[
                "P1",
                "recommendation_score",
            ],
            recommendations.loc[
                "P2",
                "recommendation_score",
            ],
        )
        self.assertLess(
            recommendations.loc[
                "P1",
                "overall_risk_score",
            ],
            recommendations.loc[
                "P2",
                "overall_risk_score",
            ],
        )
        self.assertGreater(
            recommendations.loc[
                "P1",
                "overall_confidence_score",
            ],
            recommendations.loc[
                "P2",
                "overall_confidence_score",
            ],
        )


if __name__ == "__main__":
    unittest.main()
