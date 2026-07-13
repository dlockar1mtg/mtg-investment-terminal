from terminal2.history import publish_historical_intelligence


def main():
    result = publish_historical_intelligence(
        recompute_features=False
    )

    print("\nTerminal 2.5.3 Historical Intelligence publication")
    print("=" * 60)
    print(f"Datasets published: {result['datasets']}")
    print(
        f"Historical price rows: "
        f"{result['historical_price_rows']}"
    )
    print(
        f"Monthly price rows: "
        f"{result['monthly_price_rows']}"
    )
    print(
        f"Historical return rows: "
        f"{result['historical_return_rows']}"
    )
    print(f"Coverage rows: {result['coverage_rows']}")
    print(
        f"Source-quality rows: "
        f"{result['source_quality_rows']}"
    )


if __name__ == "__main__":
    main()
