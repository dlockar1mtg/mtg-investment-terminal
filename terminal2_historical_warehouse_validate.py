from terminal2.history import validate_historical_warehouse


def main():
    result = validate_historical_warehouse()

    print("\nTerminal 2.5.3 Historical Warehouse Validation")
    print("=" * 60)
    print(f"Datasets checked: {result.datasets_checked}")
    print(
        f"Duplicate primary-key rows: "
        f"{result.duplicate_key_rows}"
    )
    print(f"Invalid date rows: {result.invalid_date_rows}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Historical intelligence datasets are "
        "standardized and valid."
    )


if __name__ == "__main__":
    main()
