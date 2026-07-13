import argparse
from pathlib import Path

from terminal2.secret_lair.imports import (
    import_secret_lair_registry,
)
from terminal2.secret_lair.registry import REGISTRY_PATH


def main():
    parser = argparse.ArgumentParser(
        description="Import a curated Secret Lair registry CSV."
    )
    parser.add_argument(
        "input_csv",
        help="Path to the completed Secret Lair import CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(REGISTRY_PATH),
        help="Local normalized registry output path.",
    )
    args = parser.parse_args()

    result = import_secret_lair_registry(
        Path(args.input_csv),
        output_path=Path(args.output),
    )

    print("\nTerminal 2.6.0 Secret Lair Registry Import")
    print("=" * 56)
    print(f"Input: {result.input_path}")
    print(f"Output: {result.output_path}")
    print(f"Imported rows: {result.imported_rows}")
    print(f"Rejected rows: {result.rejected_rows}")
    print(
        f"Duplicate IDs removed: "
        f"{result.duplicate_rows_removed}"
    )


if __name__ == "__main__":
    main()
