from pathlib import Path
import pandas as pd
from config import MARKET_INTELLIGENCE_FILE, MONTE_CARLO_OUTPUT_FILE

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
        "market_intelligence_score",
        "liquidity_proxy_score",
        "inventory_risk_proxy",
        "market_regime_score",
        "investment_feature_score",
        "mc_median",
        "mc_p05",
        "mc_p95",
        "prob_double",
        "prob_triple",
        "prob_loss",
        "simulated_cagr_base",
        "simulated_volatility",
    ] if c in df.columns]
    if len(df):
        print(df[cols].sort_values(cols[2] if len(cols) > 2 else cols[0], ascending=False).head(80).to_string(index=False))

def main():
    show(MARKET_INTELLIGENCE_FILE, "Market Intelligence")
    show(MONTE_CARLO_OUTPUT_FILE, "Monte Carlo Summary")

if __name__ == "__main__":
    main()
