from pathlib import Path
import pandas as pd
from config import (
    REAL_SIGNAL_OUTPUT_FILE,
    ROLLING_PRICE_METRICS_FILE,
    DAILY_PRICE_OBSERVATIONS_FILE,
    INVENTORY_SIGNALS_FILE,
    SALES_VELOCITY_FILE,
    DEMAND_SIGNALS_FILE,
    SCARCITY_SIGNALS_FILE,
)

def show(path, title, n=80):
    path = Path(path)
    print(f"\n--- {title} ---")
    if not path.exists():
        print(f"Missing: {path}")
        return
    df = pd.read_csv(path)
    print(f"Rows: {len(df)}")
    if not len(df):
        return
    cols = [c for c in [
        "box_name",
        "investment_product_id",
        "current_price",
        "real_signal_score",
        "real_signal_confidence",
        "inventory_signal_score",
        "inventory_signal_confidence",
        "sales_velocity_score",
        "sales_signal_confidence",
        "real_demand_score",
        "demand_signal_confidence",
        "scarcity_signal_score",
        "scarcity_signal_confidence",
        "price_trend_signal_score",
        "price_signal_confidence",
        "observations",
        "return_30d_db",
        "return_90d_db",
        "drawdown_from_ath",
    ] if c in df.columns]
    print(df[cols].head(n).to_string(index=False))

def main():
    show(REAL_SIGNAL_OUTPUT_FILE, "Real Signal Scores")
    show(ROLLING_PRICE_METRICS_FILE, "Rolling Price Metrics")
    show(DAILY_PRICE_OBSERVATIONS_FILE, "Daily Price Observations", n=20)
    show(INVENTORY_SIGNALS_FILE, "Inventory Input Template", n=20)
    show(SALES_VELOCITY_FILE, "Sales Velocity Input Template", n=20)
    show(DEMAND_SIGNALS_FILE, "Demand Input Template", n=20)
    show(SCARCITY_SIGNALS_FILE, "Scarcity Input Template", n=20)

if __name__ == "__main__":
    main()
