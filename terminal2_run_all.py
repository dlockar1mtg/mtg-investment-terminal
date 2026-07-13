from terminal2.db.schema import init_db
from terminal2.db.loaders import sync_product_master
from terminal2.features.price_features import compute_price_features
from terminal2.analytics.scoring import score_from_features
from terminal2.exports.export_reports import export_all
from terminal2.warehouse.dashboard_mart import build_dashboard_warehouse
from terminal2.db.module2_migration import migrate_module2
from terminal2.market.analytics.intelligence import compute_market_intelligence
from terminal2.market.analytics.health import compute_source_health, compute_market_health
from terminal2.market.exports import export_module2_dashboard

def main():
    init_db()
    migrate_module2()
    count = sync_product_master()
    print(f"Synced approved products: {count}")

    features = compute_price_features()
    print(f"Computed features: {len(features)}")

    ranked = score_from_features()
    print(f"Scored products: {len(ranked)}")
    if len(ranked):
        cols = [c for c in [
            "box_name","latest_price","observation_count","investment_score","risk_adjusted_score",
            "rating","buy_signal","expected_cagr","mc_median_5yr","prob_double","prob_loss"
        ] if c in ranked.columns]
        print(ranked[cols].head(30).to_string(index=False))

    outputs = export_all()
    print("\nCore exports:")
    for name, path in outputs.items():
        print(f"{name}: {path}")

    manifest, warehouse_status = build_dashboard_warehouse(create_snapshot=True)
    print("\nDashboard warehouse:")
    print(f"Datasets created: {warehouse_status['datasets_created']}")
    print(f"Products: {warehouse_status['product_rows']}")
    print(f"Historical price rows: {warehouse_status['historical_price_rows']}")
    print("Dashboard root: data/dashboard/")
    print("Analytics root: data/analytics/")

    intelligence = compute_market_intelligence()
    source_health = compute_source_health()
    market_health = compute_market_health()
    module2_status = export_module2_dashboard()
    print("\nModule 2 market intelligence:")
    print(f"Products scored: {len(intelligence)}")
    print(f"Source health rows: {len(source_health)}")
    print(f"Market health rows: {len(market_health)}")
    print(f"Module 2 dashboard datasets: {module2_status['datasets']}")
    print(f"Standardized warehouse market datasets: {module2_status['warehouse_datasets']}")
    print("Canonical Power BI market root: data/warehouse/current/")

if __name__ == "__main__":
    main()
