from pathlib import Path
import pandas as pd
from config import INVESTMENT_FEATURES_FILE, HISTORICAL_METRICS_FILE

def show(path, title):
    path = Path(path)
    print(f"\n--- {title} ---")
    if not path.exists():
        print(f"Missing: {path}")
        return
    df = pd.read_csv(path)
    print(f"Rows: {len(df)}")
    cols = [c for c in [
        "box_name",
        "current_price",
        "history_observations",
        "return_30d",
        "return_90d",
        "return_180d",
        "return_365d",
        "drawdown_from_high",
        "annualized_volatility",
        "momentum_score",
        "drawdown_score",
        "price_stability_score",
        "history_confidence",
        "investment_feature_score",
    ] if c in df.columns]
    if len(df):
        print(df[cols].head(80).to_string(index=False))

def main():
    show(INVESTMENT_FEATURES_FILE, "Investment Features")
    show(HISTORICAL_METRICS_FILE, "Historical Metrics")

if __name__ == "__main__":
    main()
