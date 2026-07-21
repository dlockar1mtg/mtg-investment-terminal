from terminal2.warehouse.dashboard_mart import (
    build_dashboard_warehouse,
)


def main():
    manifest, status = build_dashboard_warehouse(
        create_snapshot=True
    )

    print("Dashboard warehouse exports created:")
    print(f"Datasets: {status['datasets_created']}")
    print(f"Products: {status['product_rows']}")
    print(
        "Historical price rows: "
        f"{status['historical_price_rows']}"
    )
    print(f"Manifest: {manifest}")
    print("Dashboard root: data/dashboard/")
    print("Analytics root: data/analytics/")


if __name__ == "__main__":
    main()