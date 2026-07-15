from terminal2.warehouse_core import DashboardPublisher, Warehouse

from .contracts import get_return_analytics_contract
from .engine import build_universal_return_analytics


def publish_return_analytics_datasets(datasets, warehouse=None):
    publisher = DashboardPublisher(warehouse or Warehouse())
    return publisher.publish_many(
        [
            (
                frame,
                get_return_analytics_contract(name).definition(),
            )
            for name, frame in datasets.items()
        ],
        message="Terminal 2.10.1 universal return analytics",
    )


def publish_universal_return_analytics(warehouse=None):
    result = build_universal_return_analytics()
    published = publish_return_analytics_datasets(
        result.datasets,
        warehouse,
    )
    summary = result.datasets[
        "universal_return_analytics_summary"
    ].iloc[0]
    return {
        "datasets": len(published),
        "products": int(summary["product_count"]),
        "asset_classes": int(summary["asset_class_count"]),
        "analytics_ready": int(summary["analytics_ready_count"]),
        "rolling_12m_ready": int(summary["rolling_12m_ready_count"]),
        "rolling_24m_ready": int(summary["rolling_24m_ready_count"]),
        "positive_cagr": int(summary["positive_cagr_count"]),
        "negative_cagr": int(summary["negative_cagr_count"]),
        "median_cagr": float(summary["median_cagr"]),
        "status": str(summary["analytics_status"]),
    }
