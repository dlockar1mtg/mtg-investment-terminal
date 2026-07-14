from terminal2.intelligence import (
    validate_core_intelligence,
)


def main():
    result = validate_core_intelligence()

    print(
        "\nTerminal 2.8.0 Phase 1 "
        "Core Intelligence Validation"
    )
    print("=" * 64)
    print(
        f"Datasets checked: "
        f"{result.datasets_checked}"
    )
    print(
        f"Products checked: "
        f"{result.products_checked}"
    )

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Core investment intelligence "
        "is valid."
    )


if __name__ == "__main__":
    main()
