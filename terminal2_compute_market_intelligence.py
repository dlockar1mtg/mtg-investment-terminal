from terminal2.market.analytics.intelligence import compute_market_intelligence
from terminal2.market.analytics.health import compute_source_health, compute_market_health
from terminal2.market.exports import export_module2_dashboard

def main():
    intelligence = compute_market_intelligence()
    source_health = compute_source_health()
    market_health = compute_market_health()
    exports = export_module2_dashboard()

    print("\nModule 2 market intelligence complete.")
    print(f"Products scored: {len(intelligence)}")
    print(f"Source health rows: {len(source_health)}")
    print(f"Market health rows: {len(market_health)}")
    print(f"Dashboard datasets refreshed: {exports['datasets']}")

    if len(intelligence):
        cols = [c for c in [
            "box_name", "current_price", "market_intelligence_score",
            "market_intelligence_confidence", "market_relative_strength",
            "liquidity_score", "supply_signal_score", "sales_velocity_score",
            "signal_basis"
        ] if c in intelligence.columns]
        print("\nTop market intelligence results:")
        print(intelligence[cols].head(30).to_string(index=False))

if __name__ == "__main__":
    main()
