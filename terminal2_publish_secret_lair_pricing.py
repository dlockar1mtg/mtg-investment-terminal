from terminal2.secret_lair import (
    publish_secret_lair_pricing,
)


def main():
    result = publish_secret_lair_pricing()

    print("\nTerminal 2.6.1 Secret Lair Pricing")
    print("=" * 52)
    print(f"Datasets published: {result['datasets']}")
    print(f"Price file found: {result['price_file_exists']}")
    print(f"Price path: {result['price_path']}")
    print(f"Observations: {result['observation_count']}")
    print(f"Priced assets: {result['priced_asset_count']}")
    print(f"Monthly rows: {result['monthly_rows']}")
    print(f"Quality errors: {result['quality_errors']}")
    print(f"Quality warnings: {result['quality_warnings']}")
    print(
        "Warehouse root: "
        "data/warehouse/current/secret_lair/"
    )


if __name__ == "__main__":
    main()
