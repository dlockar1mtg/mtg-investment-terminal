from terminal2.secret_lair import (
    validate_secret_lair_pricing,
)


def main():
    result = validate_secret_lair_pricing()

    print("\nTerminal 2.6.1 Secret Lair Pricing Validation")
    print("=" * 58)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Price observations: {result.observation_count}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Secret Lair pricing and historical "
        "intelligence are valid."
    )


if __name__ == "__main__":
    main()
