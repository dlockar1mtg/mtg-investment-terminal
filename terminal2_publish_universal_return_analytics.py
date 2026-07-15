from terminal2.return_analytics import (
    publish_universal_return_analytics,
)


def main():
    status = publish_universal_return_analytics()
    print("\nTerminal 2.10.1 Universal Return Analytics")
    print("=" * 72)
    print(f"Datasets published: {status['datasets']}")
    print(f"Products analyzed: {status['products']}")
    print(f"Asset classes: {status['asset_classes']}")
    print(f"Analytics ready: {status['analytics_ready']}")
    print(f"Rolling 12-month ready: {status['rolling_12m_ready']}")
    print(f"Rolling 24-month ready: {status['rolling_24m_ready']}")
    print(f"Positive CAGR: {status['positive_cagr']}")
    print(f"Negative CAGR: {status['negative_cagr']}")
    print(f"Median CAGR: {status['median_cagr']:.4f}")
    print(f"Status: {status['status']}")


if __name__ == "__main__":
    main()
