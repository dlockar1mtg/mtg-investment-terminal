from terminal2.market.validation import validate_market_warehouse


def main():
    result = validate_market_warehouse()

    print("\nTerminal 2.5.2 Market Warehouse Validation")
    print("=" * 56)
    print(f"Datasets checked: {result.datasets_checked}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print("PASS: Market intelligence datasets are standardized and valid.")


if __name__ == "__main__":
    main()
