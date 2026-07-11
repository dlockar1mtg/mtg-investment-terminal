from terminal2.warehouse.dashboard_mart import build_dashboard_warehouse

def main():
    manifest, status = build_dashboard_warehouse(create_snapshot=True)
    print("\nDashboard analytics warehouse created.")
    print(f"Datasets created: {status['datasets_created']}")
    print(f"Products: {status['product_rows']}")
    print(f"Historical price rows: {status['historical_price_rows']}")
    print(f"Alerts: {status['alert_rows']}")
    print("\nDashboard root: data/dashboard/")
    print("Analytics root: data/analytics/")
    if len(manifest):
        print("\nDataset manifest:")
        print(manifest.to_string(index=False))

if __name__ == "__main__":
    main()
