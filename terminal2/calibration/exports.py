from __future__ import annotations

from terminal2.calibration.contracts import (
    get_calibration_contract,
)
from terminal2.calibration.engine import (
    build_model_calibration_datasets,
)
from terminal2.warehouse_core import (
    DashboardPublisher,
    Warehouse,
)


def publish_calibration_datasets(
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
            get_calibration_contract(
                name
            ).definition(),
        )
        for name, dataframe in datasets.items()
    ]
    return publisher.publish_many(
        batch,
        message=(
            "Terminal 2.9.0 model calibration "
            "publication"
        ),
    )


def publish_model_calibration(
    *,
    warehouse: Warehouse | None = None,
) -> dict:
    result = build_model_calibration_datasets()
    published = publish_calibration_datasets(
        result.datasets,
        warehouse=warehouse,
    )
    summary = result.datasets[
        "calibration_executive_summary"
    ].iloc[0]

    return {
        "datasets": len(published),
        "new_vintage_rows": result.new_vintage_rows,
        "archived_forecast_count": int(
            summary["archived_forecast_count"]
        ),
        "matured_forecast_count": int(
            summary["matured_forecast_count"]
        ),
        "pending_forecast_count": int(
            summary["pending_forecast_count"]
        ),
        "calibration_status": str(
            summary["calibration_status"]
        ),
        "archive_path": result.archive_path,
    }
