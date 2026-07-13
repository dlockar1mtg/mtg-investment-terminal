from terminal2.secret_lair import publish_secret_lair_registry


def main():
    result = publish_secret_lair_registry()

    print("\nTerminal 2.6.0 Secret Lair Registry")
    print("=" * 52)
    print(f"Datasets published: {result['datasets']}")
    print(f"Registry file found: {result['registry_exists']}")
    print(f"Registry path: {result['registry_path']}")
    print(f"Assets: {result['asset_count']}")
    print(f"Distinct drops: {result['drop_count']}")
    print(f"IP groups: {result['ip_count']}")
    print(f"Artists: {result['artist_count']}")
    print(f"Quality errors: {result['quality_errors']}")
    print(f"Quality warnings: {result['quality_warnings']}")
    print(
        "Warehouse root: "
        "data/warehouse/current/secret_lair/"
    )


if __name__ == "__main__":
    main()
