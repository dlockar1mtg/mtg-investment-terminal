import argparse
from pathlib import Path

from terminal2.secret_lair.price_imports import (
    import_secret_lair_prices,
)
from terminal2.secret_lair.pricing import PRICE_PATH
from terminal2.secret_lair.registry import REGISTRY_PATH


def main():
    parser = argparse.ArgumentParser(
        description="Import curated Secret Lair price observations."
    )
    parser.add_argument(
        "input_csv",
        help="Path to the completed price-observation CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(PRICE_PATH),
        help="Normalized local price-history output path.",
    )
    parser.add_argument(
        "--registry",
        default=str(REGISTRY_PATH),
        help="Secret Lair registry used to validate asset IDs.",
    )
    args = parser.parse_args()

    result = import_secret_lair_prices(
        Path(args.input_csv),
        output_path=Path(args.output),
        registry_path=Path(args.registry),
    )

    print("\nTerminal 2.6.1 Secret Lair Price Import")
    print("=" * 54)
    print(f"Input: {result.input_path}")
    print(f"Output: {result.output_path}")
    print(f"Imported rows: {result.imported_rows}")
    print(f"Rejected rows: {result.rejected_rows}")
    print(
        f"Duplicate keys removed: "
        f"{result.duplicate_rows_removed}"
    )


if __name__ == "__main__":
    main()
