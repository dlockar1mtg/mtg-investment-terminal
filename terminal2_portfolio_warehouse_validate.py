from terminal2.portfolio import validate_portfolio_warehouse


def main():
    result = validate_portfolio_warehouse()

    print("\nTerminal 2.5.4 Portfolio Warehouse Validation")
    print("=" * 58)
    print(f"Datasets checked: {result.datasets_checked}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Portfolio intelligence datasets are "
        "standardized and valid."
    )


if __name__ == "__main__":
    main()
