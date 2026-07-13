import unittest

import pandas as pd

from terminal2.portfolio.engine import build_portfolio_datasets


class PortfolioEngineTests(unittest.TestCase):
    def setUp(self):
        self.universe = pd.DataFrame({
            "investment_product_id": ["p1", "p2", "p3"],
            "box_name": ["Alpha", "Beta", "Gamma"],
            "set_name": ["A", "B", "C"],
            "product_type": [
                "Collector Booster Display",
                "Draft Booster Display",
                "Secret Lair Drop",
            ],
            "current_price": [100.0, 200.0, 50.0],
            "investment_score": [80.0, 70.0, 60.0],
            "risk_adjusted_score": [78.0, 68.0, 58.0],
            "market_intelligence_score": [75.0, 65.0, 55.0],
            "market_intelligence_confidence": [70.0, 60.0, 50.0],
            "expected_cagr": [0.15, 0.12, 0.09],
            "projection_confidence": [80.0, 70.0, 60.0],
            "prob_loss": [0.15, 0.25, 0.35],
            "annualized_volatility": [0.20, 0.30, 0.40],
            "mc_median_5yr": [200.0, 350.0, 75.0],
            "buy_signal": ["Buy", "Watch", "Wait"],
        })
        self.holdings = pd.DataFrame({
            "investment_product_id": ["p1", "p2"],
            "quantity": [2.0, 1.0],
            "acquisition_cost_total": [150.0, 180.0],
            "acquisition_date": ["2025-01-01", "2025-06-01"],
            "notes": ["", ""],
        })

    def test_portfolio_build(self):
        result = build_portfolio_datasets(
            self.universe,
            self.holdings,
            model_capital=10000.0,
            maximum_positions=3,
        )
        datasets = result.datasets

        self.assertEqual(len(datasets["portfolio_positions"]), 2)
        self.assertGreater(
            len(datasets["portfolio_candidate_allocation"]), 0
        )
        self.assertAlmostEqual(
            datasets["portfolio_candidate_allocation"][
                "target_weight"
            ].sum(),
            1.0,
            places=4,
        )
        self.assertEqual(
            len(datasets["portfolio_summary"]), 1
        )
        self.assertEqual(
            len(datasets["portfolio_scenarios"]), 6
        )

    def test_no_holdings_still_builds_model_portfolio(self):
        result = build_portfolio_datasets(
            self.universe,
            pd.DataFrame(columns=self.holdings.columns),
            holdings_file_found=False,
        )
        self.assertTrue(
            result.datasets["portfolio_positions"].empty
        )
        self.assertGreater(
            len(result.datasets["portfolio_candidate_allocation"]),
            0,
        )


if __name__ == "__main__":
    unittest.main()
