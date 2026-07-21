from terminal2.db.module2_migration import migrate_module2
from terminal2.db.loaders import sync_product_master
from terminal2.features.price_features import compute_price_features
from terminal2.analytics.scoring import score_from_features
from terminal2.market.sources.importers import import_all_market_inputs
from terminal2.market.analytics.intelligence import compute_market_intelligence
from terminal2.market.analytics.health import compute_source_health, compute_market_health
from terminal2.warehouse.dashboard_mart import build_dashboard_warehouse
from terminal2.market.exports import export_module2_dashboard
from terminal2.warehouse_migration import migrate_legacy_dashboard_outputs

def main():
    migrate_module2()
    print("Module 2 database ready.")

    products = sync_product_master()
    print(f"Synced approved products: {products}")

    imported = import_all_market_inputs()
    print(f"Supply rows imported: {imported['supply']['rows_imported']}")
    print(f"Sales rows imported: {imported['sales']['rows_imported']}")

    features = compute_price_features()
    print(f"Computed price features: {len(features)}")

    ranked = score_from_features()
    print(f"Scored products: {len(ranked)}")

    intelligence = compute_market_intelligence()
    print(f"Computed market intelligence: {len(intelligence)}")

    source_health = compute_source_health()
    market_health = compute_market_health()
    print(f"Source health rows: {len(source_health)}")
    print(f"Market health rows: {len(market_health)}")

    manifest, status = build_dashboard_warehouse(create_snapshot=True)
    migration_status = migrate_legacy_dashboard_outputs(
        create_snapshots=True,
        include_analytics_current=True,
        continue_on_error=False,
    )
    module2_status = export_module2_dashboard()

    print("\nFull Module 2 workflow complete.")
    print(f"Base dashboard datasets: {status['datasets_created']}")
    print(f"Module 2 dashboard datasets: {module2_status['datasets']}")
    print(f"Standardized warehouse market datasets: {module2_status['warehouse_datasets']}")
    print(f"Products: {status['product_rows']}")
    print(f"Historical price rows: {status['historical_price_rows']}")
    print(f"Market intelligence rows: {module2_status['market_intelligence_rows']}")
    print(f"Warehouse datasets migrated: {migration_status['datasets_migrated']}")
    print("Dashboard root: data/dashboard/ (legacy compatibility)")
    print("Analytics root: data/analytics/ (legacy compatibility)")
    print("Canonical Power BI root: data/warehouse/current/")

if __name__ == "__main__":
    main()
