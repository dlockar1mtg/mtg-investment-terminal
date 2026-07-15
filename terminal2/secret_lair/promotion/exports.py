from __future__ import annotations
from terminal2.warehouse_core import DashboardPublisher, Warehouse
from .contracts import get_promotion_contract
from .engine import build_secret_lair_promotion_plan

def publish_promotion_datasets(datasets, *, warehouse=None):
    publisher = DashboardPublisher(warehouse or Warehouse())
    return publisher.publish_many(
        [
            (frame, get_promotion_contract(name).definition())
            for name, frame in datasets.items()
        ],
        message="Terminal 2.9.8 production registry promotion status",
    )

def publish_secret_lair_promotion(*, warehouse=None, minimum_confidence=75):
    plan = build_secret_lair_promotion_plan(
        minimum_confidence=minimum_confidence
    )
    published = publish_promotion_datasets(
        plan.datasets, warehouse=warehouse
    )
    summary = plan.datasets[
        "secret_lair_promotion_summary"
    ].iloc[0]
    return {
        "datasets": len(published),
        "master_products": int(summary["master_product_count"]),
        "eligible_products": int(summary["eligible_product_count"]),
        "rejected_products": int(summary["rejected_product_count"]),
        "review_remaining": int(summary["review_remaining_count"]),
        "eligible_prices": int(summary["eligible_price_count"]),
        "production_registry": int(summary["production_registry_count"]),
        "production_prices": int(summary["production_price_count"]),
        "apply_ready": bool(summary["apply_ready"]),
        "last_apply_status": str(summary["last_apply_status"]),
    }
