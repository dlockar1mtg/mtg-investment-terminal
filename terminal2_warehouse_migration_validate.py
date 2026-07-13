from terminal2.warehouse_migration import validate_migration


def main():
    result = validate_migration()

    print("\nTerminal 2.5.1c Migration Validation")
    print("=" * 52)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Datasets missing: {result.datasets_missing}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Warehouse migration is complete and valid."
    )


if __name__ == "__main__":
    main()
