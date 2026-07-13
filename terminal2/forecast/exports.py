from __future__ import annotations

import pandas as pd

from terminal2.db.module2_migration import migrate_module2
from terminal2.db.schema import get_connection
from terminal2.forecast.contracts import get_forecast_contract
from terminal2.forecast.engine import build_forecast_datasets
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def load_forecast_universe() -> pd.DataFrame:
    migrate_module2()
    connection = get_connection()
    try:
        return pd.read_sql_query(
            """
            SELECT
                p.investment_product_id,
                p.box_name,
                p.set_name,
                p.product_type,
                p.approval_status,
                s.current_price,
                s.investment_score,
                s.risk_adjusted_score,
                s.expected_cagr,
                s.projection_confidence,
                s.prob_loss,
                f.observation_count,
                f.return_30d,
                f.return_90d,
                f.return_180d,
                f.return_365d,
                f.annualized_volatility,
                f.trend_score,
                f.history_confidence,
                mi.market_intelligence_score,
                mi.market_intelligence_confidence,
                mi.supply_signal_score,
                mi.sales_velocity_score,
                mi.liquidity_score
            FROM products p
            LEFT JOIN investment_scores s
              ON s.investment_product_id = p.investment_product_id
            LEFT JOIN product_features f
              ON f.investment_product_id = p.investment_product_id
            LEFT JOIN market_intelligence mi
              ON mi.investment_product_id = p.investment_product_id
            WHERE LOWER(COALESCE(p.approval_status, '')) = 'approved'
            """,
            connection,
        )
    finally:
        connection.close()


def publish_forecast_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            dataframe,
            get_forecast_contract(name).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.5.5 forecast intelligence publication",
    )


def publish_forecast_intelligence(
    *,
    warehouse: Warehouse | None = None,
) -> dict:
    universe = load_forecast_universe()
    result = build_forecast_datasets(universe)
    published = publish_forecast_datasets(
        result.datasets,
        warehouse=warehouse,
    )
    rankings = result.datasets["forecast_rankings"]
    summary = result.datasets["forecast_market_summary"].iloc[0]
    return {
        "datasets": len(published),
        "product_count": len(result.datasets["forecast_product_summary"]),
        "horizon_rows": len(result.datasets["forecast_horizons"]),
        "bullish_products": int(summary["bullish_product_count"]),
        "bearish_products": int(summary["bearish_product_count"]),
        "average_conviction_score": float(summary["average_conviction_score"]),
        "highest_conviction_product": (
            rankings.iloc[0]["box_name"] if len(rankings) else ""
        ),
    }
