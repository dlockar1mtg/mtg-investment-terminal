from terminal2.calibration import (
    validate_model_calibration,
)


def main():
    result = validate_model_calibration()

    print(
        "\nTerminal 2.9.0 "
        "Model Calibration Validation"
    )
    print("=" * 58)
    print(
        f"Datasets checked: "
        f"{result.datasets_checked}"
    )
    print(
        f"Archived forecasts: "
        f"{result.archived_forecasts}"
    )
    print(
        f"Matured forecasts: "
        f"{result.matured_forecasts}"
    )

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if not result.passed:
        raise SystemExit(1)

    print(
        "PASS: Model calibration outputs are valid."
    )


if __name__ == "__main__":
    main()
