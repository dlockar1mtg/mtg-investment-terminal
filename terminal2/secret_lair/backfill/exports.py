from __future__ import annotations

from terminal2.secret_lair.backfill.contracts import (
    get_secret_lair_backfill_contract,
)
from terminal2.secret_lair.backfill.engine import (
    build_secret_lair_backfill,
)
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def publish_secret_lair_backfill_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            dataframe,
            get_secret_lair_backfill_contract(
                name
            ).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.6.2 Secret Lair backfill publication",
    )


def publish_secret_lair_backfill(
    *,
    warehouse: Warehouse | None = None,
) -> dict:
    result = build_secret_lair_backfill()
    published = publish_secret_lair_backfill_datasets(
        result.datasets,
        warehouse=warehouse,
    )
    summary = result.datasets[
        "secret_lair_backfill_summary"
    ].iloc[0]
    return {
        "datasets": len(published),
        "catalog_exists": result.catalog_exists,
        "prices_exist": result.prices_exist,
        "overrides_exist": result.overrides_exist,
        "catalog_rows": int(summary["catalog_rows"]),
        "matched_rows": int(summary["matched_rows"]),
        "new_asset_rows": int(summary["new_asset_rows"]),
        "review_rows": int(summary["review_rows"]),
        "price_rows": int(summary["price_rows"]),
        "apply_ready": bool(summary["apply_ready"]),
    }
