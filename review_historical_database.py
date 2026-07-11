from models.historical_importer import summarize_historical_database
from config import DAILY_PRICE_OBSERVATIONS_FILE, ROLLING_PRICE_METRICS_FILE
from pathlib import Path
import pandas as pd

def main():
    print("\n--- Historical Database Summary ---")
    summary = summarize_historical_database()
    if summary.empty:
        print(f"No historical observations found at {DAILY_PRICE_OBSERVATIONS_FILE}")
    else:
        print(summary.head(100).to_string(index=False))

    print("\n--- Rolling Metrics Preview ---")
    path = Path(ROLLING_PRICE_METRICS_FILE)
    if not path.exists():
        print(f"Missing: {path}")
    else:
        df = pd.read_csv(path)
        print(f"Rows: {len(df)}")
        cols = [c for c in [
            "box_name", "observations", "current_price_db", "ma_30d", "ma_90d",
            "return_30d_db", "return_90d_db", "return_180d_db",
            "drawdown_from_ath", "annualized_volatility_db"
        ] if c in df.columns]
        if len(df):
            print(df[cols].head(100).to_string(index=False))

if __name__ == "__main__":
    main()
