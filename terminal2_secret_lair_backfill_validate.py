from terminal2.secret_lair.backfill import (
    validate_secret_lair_backfill,
)


def main():
    result = validate_secret_lair_backfill()

    print("\nTerminal 2.6.2 Secret Lair Backfill Validation")
    print("=" * 60)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Source catalog rows: {result.catalog_rows}")
    print(f"Manual review rows: {result.review_rows}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Secret Lair catalog backfill and "
        "source integration are valid."
    )


if __name__ == "__main__":
    main()
