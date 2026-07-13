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
from terminal2.history import publish_historical_intelligence
from terminal2.portfolio import publish_portfolio_intelligence
from terminal2.forecast import publish_forecast_intelligence
from terminal2.semantic import publish_semantic_layer
from terminal2.secret_lair import publish_secret_lair_registry

def main():
    init_db()
    migrate_module2()
    count = sync_product_master()
    print(f"Synced approved products: {count}")

    features = compute_price_features()
    print(f"Computed features: {len(features)}")

    historical_status = publish_historical_intelligence(
        recompute_features=False
    )
    print("\nHistorical intelligence:")
    print(f"Datasets published: {historical_status['datasets']}")
    print(f"Historical price rows: {historical_status['historical_price_rows']}")
    print(f"Monthly price rows: {historical_status['monthly_price_rows']}")
    print(f"Historical return rows: {historical_status['historical_return_rows']}")

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

    forecast_status = publish_forecast_intelligence()
    print("\nForecast intelligence:")
    print(f"Datasets published: {forecast_status['datasets']}")
    print(f"Products forecast: {forecast_status['product_count']}")
    print(f"Horizon rows: {forecast_status['horizon_rows']}")
    print(f"Average conviction: {forecast_status['average_conviction_score']:.2f}")
    print("Canonical Power BI forecast root: data/warehouse/current/intelligence/")

    portfolio_status = publish_portfolio_intelligence(
        model_capital=10000.0,
        maximum_positions=12,
    )
    print("\nPortfolio intelligence:")
    print(f"Datasets published: {portfolio_status['datasets']}")
    print(f"Holdings file found: {portfolio_status['holdings_file_found']}")
    print(f"Actual positions: {portfolio_status['position_count']}")
    print(f"Model candidates: {portfolio_status['candidate_count']}")
    print("Canonical Power BI portfolio root: data/warehouse/current/portfolio/")

    semantic_status = publish_semantic_layer()
    print("\nPower BI semantic layer:")
    print(f"Datasets published: {semantic_status['datasets']}")
    print(f"Products: {semantic_status['products']}")
    print(f"Calendar rows: {semantic_status['calendar_rows']}")
    print(f"Executive KPIs: {semantic_status['executive_kpis']}")
    print("Canonical semantic root: data/warehouse/current/semantic/")

    secret_lair_status = publish_secret_lair_registry()
    print("\nSecret Lair registry:")
    print(f"Datasets published: {secret_lair_status['datasets']}")
    print(f"Registry assets: {secret_lair_status['asset_count']}")
    print(f"Distinct drops: {secret_lair_status['drop_count']}")
    print("Canonical Secret Lair root: data/warehouse/current/secret_lair/")

if __name__ == "__main__":
    main()
