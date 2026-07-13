from terminal2.warehouse_migration import (
    migrate_legacy_dashboard_outputs,
)


def main():
    result = migrate_legacy_dashboard_outputs()

    print("\nTerminal 2.5.1c Warehouse Migration complete.")
    print(f"Status: {result['status']}")
    print(
        f"Datasets discovered: "
        f"{result['datasets_discovered']}"
    )
    print(
        f"Datasets migrated: "
        f"{result['datasets_migrated']}"
    )
    print(f"Datasets failed: {result['datasets_failed']}")
    print(f"Warnings: {result['warning_count']}")
    print(f"Warehouse root: {result['warehouse_root']}")
    print(f"Migration report: {result['migration_report']}")


if __name__ == "__main__":
    main()
