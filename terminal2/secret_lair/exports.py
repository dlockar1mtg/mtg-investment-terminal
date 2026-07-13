from __future__ import annotations

from pathlib import Path

from terminal2.secret_lair.contracts import (
    get_secret_lair_contract,
)
from terminal2.secret_lair.registry import (
    REGISTRY_PATH,
    build_secret_lair_datasets,
)
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def publish_secret_lair_datasets(
    datasets,
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            dataframe,
            get_secret_lair_contract(name).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.6.0 Secret Lair registry publication",
    )


def publish_secret_lair_registry(
    *,
    registry_path: Path = REGISTRY_PATH,
    warehouse: Warehouse | None = None,
) -> dict:
    result = build_secret_lair_datasets(
        registry_path=registry_path
    )
    published = publish_secret_lair_datasets(
        result.datasets,
        warehouse=warehouse,
    )
    quality = result.datasets["secret_lair_data_quality"]
    return {
        "datasets": len(published),
        "registry_exists": result.registry_exists,
        "registry_path": result.registry_path,
        "asset_count": len(
            result.datasets["secret_lair_registry"]
        ),
        "drop_count": int(
            result.datasets["secret_lair_registry"][
                "drop_name"
            ].nunique()
        )
        if not result.datasets["secret_lair_registry"].empty
        else 0,
        "ip_count": len(
            result.datasets["secret_lair_ip_catalog"]
        ),
        "artist_count": int(
            result.datasets["secret_lair_artist_catalog"][
                "artist_name"
            ].nunique()
        )
        if not result.datasets[
            "secret_lair_artist_catalog"
        ].empty
        else 0,
        "quality_errors": int(
            quality["severity"].eq("Error").sum()
        )
        if not quality.empty
        else 0,
        "quality_warnings": int(
            quality["severity"].eq("Warning").sum()
        )
        if not quality.empty
        else 0,
    }
