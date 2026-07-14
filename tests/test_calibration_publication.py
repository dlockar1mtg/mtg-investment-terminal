from pathlib import Path
import tempfile
import unittest

import pandas as pd

from terminal2.calibration.contracts import (
    CALIBRATION_DATASET_CONTRACTS,
)
from terminal2.calibration.exports import (
    publish_calibration_datasets,
)
from terminal2.warehouse_core import (
    Warehouse,
    get_warehouse_config,
)


class CalibrationPublicationTests(unittest.TestCase):
    def test_empty_compatible_publication(self):
        datasets = {}
        for (
            name,
            contract,
        ) in CALIBRATION_DATASET_CONTRACTS.items():
            datasets[name] = pd.DataFrame(
                columns=contract.required_columns
            )

        datasets[
            "calibration_executive_summary"
        ] = pd.DataFrame(
            [
                {
                    "snapshot_date": "2026-07-14",
                    "archived_forecast_count": 0,
                    "matured_forecast_count": 0,
                    "pending_forecast_count": 0,
                    "mean_absolute_error": pd.NA,
                    "mean_absolute_percentage_error": pd.NA,
                    "root_mean_squared_error": pd.NA,
                    "directional_accuracy": pd.NA,
                    "recommendation_hit_rate": pd.NA,
                    "calibration_status": (
                        "Insufficient Matured Forecasts"
                    ),
                }
            ]
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            warehouse = Warehouse(
                config=get_warehouse_config(root)
            )
            published = (
                publish_calibration_datasets(
                    datasets,
                    warehouse=warehouse,
                )
            )
            self.assertEqual(len(published), 8)
            self.assertTrue(
                (
                    root
                    / "data"
                    / "warehouse"
                    / "current"
                    / "calibration"
                    / "calibration_executive_summary.csv"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
