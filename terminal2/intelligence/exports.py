from __future__ import annotations

from terminal2.forecast.exports import (
    load_forecast_universe,
)
from terminal2.intelligence.contracts import (
    get_intelligence_contract,
)
from terminal2.intelligence.engine import (
    build_core_intelligence_datasets,
)
from terminal2.warehouse_core import (
    DashboardPublisher,
    Warehouse,
)


def publish_intelligence_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(
        warehouse or Warehouse()
    )
    batch = [
        (
            dataframe,
            get_intelligence_contract(
                name
            ).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message=(
            "Terminal 2.8.0 Phase 1 core "
            "investment intelligence publication"
        ),
    )


def publish_core_investment_intelligence(
    *,
    warehouse: Warehouse | None = None,
) -> dict:
    universe = load_forecast_universe()
    result = build_core_intelligence_datasets(
        universe
    )
    published = publish_intelligence_datasets(
        result.datasets,
        warehouse=warehouse,
    )

    recommendations = result.datasets[
        "intelligence_recommendations"
    ]
    buy_list = result.datasets[
        "intelligence_executive_buy_list"
    ]
    return {
        "datasets": len(published),
        "product_count": len(recommendations),
        "strong_buy_count": int(
            recommendations[
                "recommendation"
            ].eq("Strong Buy").sum()
        ),
        "buy_count": int(
            recommendations[
                "recommendation"
            ].eq("Buy").sum()
        ),
        "watch_count": int(
            recommendations[
                "recommendation"
            ].eq("Watch").sum()
        ),
        "buy_list_count": len(buy_list),
        "average_confidence": float(
            recommendations[
                "overall_confidence_score"
            ].mean()
        ),
        "average_risk": float(
            recommendations[
                "overall_risk_score"
            ].mean()
        ),
    }
