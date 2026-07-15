from terminal2.return_analytics import (
    validate_universal_return_analytics,
)


def main():
    result = validate_universal_return_analytics()
    print("\nTerminal 2.10.1 Universal Return Analytics Validation")
    print("=" * 72)
    print(f"Datasets checked: {result.datasets_checked}")
    print(f"Products analyzed: {result.products}")
    print(f"Asset classes: {result.asset_classes}")
    print(f"Analytics ready: {result.analytics_ready}")
    print(f"Rolling 12-month ready: {result.rolling_12m_ready}")
    print(f"Rolling 24-month ready: {result.rolling_24m_ready}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    if not result.passed:
        raise SystemExit(1)
    print("PASS: Universal return analytics are valid.")


if __name__ == "__main__":
    main()
