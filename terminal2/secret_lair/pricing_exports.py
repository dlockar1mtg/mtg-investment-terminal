from __future__ import annotations

from pathlib import Path

from terminal2.secret_lair.pricing import (
    PRICE_PATH,
    build_secret_lair_pricing_datasets,
)
from terminal2.secret_lair.pricing_contracts import (
    get_secret_lair_pricing_contract,
)
from terminal2.secret_lair.registry import REGISTRY_PATH
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def publish_secret_lair_pricing_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            dataframe,
            get_secret_lair_pricing_contract(name).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.6.1 Secret Lair pricing publication",
    )


def publish_secret_lair_pricing(
    *,
    registry_path: Path = REGISTRY_PATH,
    price_path: Path = PRICE_PATH,
    warehouse: Warehouse | None = None,
) -> dict:
    result = build_secret_lair_pricing_datasets(
        registry_path=registry_path,
        price_path=price_path,
    )
    published = publish_secret_lair_pricing_datasets(
        result.datasets,
        warehouse=warehouse,
    )
    quality = result.datasets["secret_lair_price_quality"]
    return {
        "datasets": len(published),
        "price_file_exists": result.price_file_exists,
        "price_path": result.price_path,
        "observation_count": len(
            result.datasets["secret_lair_price_observations"]
        ),
        "priced_asset_count": len(
            result.datasets["secret_lair_current_prices"]
        ),
        "monthly_rows": len(
            result.datasets["secret_lair_monthly_prices"]
        ),
        "quality_errors": int(
            quality["severity"].eq("Error").sum()
        ) if not quality.empty else 0,
        "quality_warnings": int(
            quality["severity"].eq("Warning").sum()
        ) if not quality.empty else 0,
    }
