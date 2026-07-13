from terminal2.semantic import publish_semantic_layer


def main():
    result = publish_semantic_layer()

    print("\nTerminal 2.5.6 Power BI Semantic Layer")
    print("=" * 58)
    print(f"Datasets published: {result['datasets']}")
    print(f"Products: {result['products']}")
    print(f"Calendar rows: {result['calendar_rows']}")
    print(
        f"Product snapshot rows: "
        f"{result['product_snapshot_rows']}"
    )
    print(
        f"Price-history rows: "
        f"{result['price_history_rows']}"
    )
    print(f"Forecast rows: {result['forecast_rows']}")
    print(f"Portfolio rows: {result['portfolio_rows']}")
    print(f"Executive KPIs: {result['executive_kpis']}")
    print(f"Source datasets monitored: {result['source_datasets']}")
    print(
        "Power BI semantic root: "
        "data/warehouse/current/semantic/"
    )


if __name__ == "__main__":
    main()
