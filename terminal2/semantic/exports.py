from __future__ import annotations

from terminal2.semantic.contracts import get_semantic_contract
from terminal2.semantic.engine import build_semantic_datasets
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def publish_semantic_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            dataframe,
            get_semantic_contract(name).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.5.6 Power BI semantic layer publication",
    )


def publish_semantic_layer(
    *,
    warehouse: Warehouse | None = None,
) -> dict:
    result = build_semantic_datasets(
        project_root=(
            warehouse.config.project_root
            if warehouse is not None
            else None
        )
    )
    published = publish_semantic_datasets(
        result.datasets,
        warehouse=warehouse,
    )

    datasets = result.datasets
    return {
        "datasets": len(published),
        "products": len(datasets["semantic_dim_product"]),
        "calendar_rows": len(datasets["semantic_dim_date"]),
        "product_snapshot_rows": len(
            datasets["semantic_fact_product_snapshot"]
        ),
        "price_history_rows": len(
            datasets["semantic_fact_price_history"]
        ),
        "forecast_rows": len(
            datasets["semantic_fact_forecast"]
        ),
        "portfolio_rows": len(
            datasets["semantic_fact_portfolio"]
        ),
        "executive_kpis": len(
            datasets["semantic_executive_kpis"]
        ),
        "source_datasets": result.source_dataset_count,
    }
