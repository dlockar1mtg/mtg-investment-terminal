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
from terminal2.intelligence import publish_core_investment_intelligence
from terminal2.calibration import publish_model_calibration
from terminal2.semantic import publish_semantic_layer
from terminal2.secret_lair import (
    publish_secret_lair_acquisition,
    publish_secret_lair_backfill,
    has_enabled_discovery_sources,
    publish_secret_lair_discovery,
    publish_secret_lair_pricing,
    publish_secret_lair_registry,
)

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

    core_intelligence = publish_core_investment_intelligence()
    print("\nCore investment intelligence:")
    print(f"Datasets published: {core_intelligence['datasets']}")
    print(f"Products assessed: {core_intelligence['product_count']}")
    print(f"Strong Buy: {core_intelligence['strong_buy_count']}")
    print(f"Buy: {core_intelligence['buy_count']}")
    print(f"Watch: {core_intelligence['watch_count']}")
    print(f"Average confidence: {core_intelligence['average_confidence']:.2f}")
    print(f"Average risk: {core_intelligence['average_risk']:.2f}")

    calibration = publish_model_calibration()
    print("\nModel calibration:")
    print(f"Datasets published: {calibration['datasets']}")
    print(f"New vintage rows: {calibration['new_vintage_rows']}")
    print(f"Archived forecasts: {calibration['archived_forecast_count']}")
    print(f"Matured forecasts: {calibration['matured_forecast_count']}")
    print(f"Pending forecasts: {calibration['pending_forecast_count']}")
    print(f"Calibration status: {calibration['calibration_status']}")

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

    secret_lair_pricing = publish_secret_lair_pricing()
    print("\nSecret Lair pricing:")
    print(f"Datasets published: {secret_lair_pricing['datasets']}")
    print(f"Price observations: {secret_lair_pricing['observation_count']}")
    print(f"Priced assets: {secret_lair_pricing['priced_asset_count']}")
    print(f"Monthly rows: {secret_lair_pricing['monthly_rows']}")

    secret_lair_backfill = publish_secret_lair_backfill()
    print("\nSecret Lair backfill:")
    print(f"Datasets published: {secret_lair_backfill['datasets']}")
    print(f"Catalog rows: {secret_lair_backfill['catalog_rows']}")
    print(f"Matched rows: {secret_lair_backfill['matched_rows']}")
    print(f"Review rows: {secret_lair_backfill['review_rows']}")
    print(f"Apply ready: {secret_lair_backfill['apply_ready']}")

    if has_enabled_discovery_sources():
        discovery = publish_secret_lair_discovery()
        print("\nAutomated Secret Lair discovery:")
        print(f"Datasets published: {discovery['datasets']}")
        print(f"Enabled sources: {discovery['enabled_sources']}")
        print(f"Discovered rows: {discovery['discovered_rows']}")
        print(f"New candidates: {discovery['new_candidate_rows']}")
        print(f"Conflict rows: {discovery['conflict_rows']}")
        print(
            "Acquisition stage ready: "
            f"{discovery['stage_ready']}"
        )
    else:
        print(
            "\nAutomated Secret Lair discovery: "
            "SKIPPED (no enabled sources)"
        )

    acquisition = publish_secret_lair_acquisition()
    print("\nSecret Lair source acquisition:")
    print(f"Datasets published: {acquisition['datasets']}")
    print(f"Enabled sources: {acquisition['enabled_sources']}")
    print(f"Catalog rows: {acquisition['catalog_rows']}")
    print(f"Conflict rows: {acquisition['conflict_rows']}")
    print(f"Backfill ready: {acquisition['backfill_ready']}")

if __name__ == "__main__":
    main()
