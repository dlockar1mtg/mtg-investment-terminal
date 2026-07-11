from pathlib import Path
import pandas as pd
from config import CONSENSUS_PRICE_FILE, SOURCE_CACHE_DIR

def main():
    consensus_file = Path(CONSENSUS_PRICE_FILE)
    sources_file = Path(SOURCE_CACHE_DIR) / "all_price_sources.csv"

    if consensus_file.exists():
        print("\nConsensus prices:")
        df = pd.read_csv(consensus_file)
        print(df.sort_values("consensus_market_price", ascending=False).head(80).to_string(index=False))
    else:
        print("No consensus file found yet. Run python run.py first.")

    if sources_file.exists():
        print("\nAll price sources:")
        src = pd.read_csv(sources_file)
        print(src.sort_values(["box_name", "market_price"]).head(200).to_string(index=False))
    else:
        print("No all_price_sources.csv found yet.")

if __name__ == "__main__":
    main()
