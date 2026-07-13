from terminal2.secret_lair import (
    validate_secret_lair_warehouse,
)


def main():
    result = validate_secret_lair_warehouse()

    print("\nTerminal 2.6.0 Secret Lair Validation")
    print("=" * 52)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Registry assets: {result.registry_assets}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Secret Lair registry foundation is valid."
    )


if __name__ == "__main__":
    main()
