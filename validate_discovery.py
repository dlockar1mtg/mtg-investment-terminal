from pathlib import Path
import pandas as pd
from config import DISCOVERED_PRODUCTS_FILE, DISCOVERED_MODEL_INPUT_FILE

def main():
    if not Path(DISCOVERED_PRODUCTS_FILE).exists():
        print("No discovered product file found yet. Run python update_prices.py first.")
        return

    df = pd.read_csv(DISCOVERED_PRODUCTS_FILE)
    print(f"Discovered collector booster products: {len(df)}")
    if len(df):
        print(df[[
            "box_name",
            "official_product_name",
            "tcgplayer_product_id",
            "tcgcsv_group_id",
            "market_price",
            "low_price",
            "price_source"
        ]].head(50).to_string(index=False))

    if Path(DISCOVERED_MODEL_INPUT_FILE).exists():
        model = pd.read_csv(DISCOVERED_MODEL_INPUT_FILE)
        print(f"Model input rows: {len(model)}")

if __name__ == "__main__":
    main()
