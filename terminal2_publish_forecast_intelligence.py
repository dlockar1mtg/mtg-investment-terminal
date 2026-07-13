from terminal2.forecast import publish_forecast_intelligence


def main():
    result = publish_forecast_intelligence()

    print("\nTerminal 2.5.5 Forecast Intelligence")
    print("=" * 54)
    print(f"Datasets published: {result['datasets']}")
    print(f"Products forecast: {result['product_count']}")
    print(f"Horizon rows: {result['horizon_rows']}")
    print(f"Bullish products: {result['bullish_products']}")
    print(f"Bearish products: {result['bearish_products']}")
    print(
        f"Average conviction: "
        f"{result['average_conviction_score']:.2f}"
    )
    print(
        f"Highest conviction: "
        f"{result['highest_conviction_product']}"
    )


if __name__ == "__main__":
    main()
