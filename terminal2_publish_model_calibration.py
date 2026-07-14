from terminal2.calibration import (
    publish_model_calibration,
)


def main():
    result = publish_model_calibration()

    print(
        "\nTerminal 2.9.0 Model Calibration Engine"
    )
    print("=" * 58)
    print(
        f"Datasets published: "
        f"{result['datasets']}"
    )
    print(
        f"New forecast vintage rows: "
        f"{result['new_vintage_rows']}"
    )
    print(
        f"Archived forecasts: "
        f"{result['archived_forecast_count']}"
    )
    print(
        f"Matured forecasts: "
        f"{result['matured_forecast_count']}"
    )
    print(
        f"Pending forecasts: "
        f"{result['pending_forecast_count']}"
    )
    print(
        f"Calibration status: "
        f"{result['calibration_status']}"
    )
    print(
        f"Local archive: "
        f"{result['archive_path']}"
    )
    print(
        "Warehouse root: "
        "data/warehouse/current/calibration/"
    )


if __name__ == "__main__":
    main()
