import argparse

from terminal2.secret_lair.backfill import (
    apply_secret_lair_backfill,
    build_secret_lair_backfill,
)
from terminal2.secret_lair.backfill.exports import (
    publish_secret_lair_backfill_datasets,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build, publish, and optionally apply the "
            "Secret Lair catalog and pricing backfill."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Write the proposed registry and price history "
            "to local working files. Default is dry-run."
        ),
    )
    args = parser.parse_args()

    result = build_secret_lair_backfill()
    publish_secret_lair_backfill_datasets(
        result.datasets
    )
    summary = result.datasets[
        "secret_lair_backfill_summary"
    ].iloc[0]

    print("\nTerminal 2.6.2 Secret Lair Backfill")
    print("=" * 54)
    print(f"Catalog file found: {result.catalog_exists}")
    print(f"Price file found: {result.prices_exist}")
    print(f"Override file found: {result.overrides_exist}")
    print(f"Catalog rows: {int(summary['catalog_rows'])}")
    print(f"Matched rows: {int(summary['matched_rows'])}")
    print(f"New assets: {int(summary['new_asset_rows'])}")
    print(f"Review rows: {int(summary['review_rows'])}")
    print(f"Price rows: {int(summary['price_rows'])}")
    print(f"Apply ready: {bool(summary['apply_ready'])}")
    print("Mode: APPLY" if args.apply else "Mode: DRY RUN")

    if args.apply:
        applied = apply_secret_lair_backfill(result)
        print(
            f"Registry rows written: "
            f"{applied.registry_rows_written}"
        )
        print(
            f"Price rows written: "
            f"{applied.price_rows_written}"
        )
        print(f"Apply log: {applied.apply_log_path}")


if __name__ == "__main__":
    main()
