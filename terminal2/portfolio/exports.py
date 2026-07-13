from __future__ import annotations

from terminal2.portfolio.contracts import get_portfolio_contract
from terminal2.portfolio.engine import (
    build_portfolio_datasets,
    load_portfolio_holdings,
    load_portfolio_universe,
)
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def publish_portfolio_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            dataframe,
            get_portfolio_contract(name).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.5.4 portfolio intelligence publication",
    )


def publish_portfolio_intelligence(
    *,
    model_capital: float = 10000.0,
    maximum_positions: int = 12,
    warehouse: Warehouse | None = None,
) -> dict:
    universe = load_portfolio_universe()
    holdings, holdings_file_found = load_portfolio_holdings()
    result = build_portfolio_datasets(
        universe,
        holdings,
        model_capital=model_capital,
        maximum_positions=maximum_positions,
        holdings_file_found=holdings_file_found,
    )
    published = publish_portfolio_datasets(
        result.datasets,
        warehouse=warehouse,
    )
    return {
        "datasets": len(published),
        "holdings_file_found": holdings_file_found,
        "position_count": len(
            result.datasets["portfolio_positions"]
        ),
        "candidate_count": len(
            result.datasets["portfolio_candidate_allocation"]
        ),
        "recommendation_count": len(
            result.datasets["portfolio_recommendations"]
        ),
        "model_capital": result.model_capital,
    }
