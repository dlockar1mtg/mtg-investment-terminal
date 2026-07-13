from terminal2.semantic import validate_semantic_layer


def main():
    result = validate_semantic_layer()

    print("\nTerminal 2.5.6 Semantic Layer Validation")
    print("=" * 58)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Orphan relationship rows: {result.orphan_rows}")

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Power BI semantic layer and executive "
        "dashboard contracts are valid."
    )


if __name__ == "__main__":
    main()
