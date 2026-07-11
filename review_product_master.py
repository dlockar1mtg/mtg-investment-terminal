from pathlib import Path
import pandas as pd

from config import PRODUCT_MASTER_FILE, PRODUCT_SELECTION_REVIEW_FILE, PRODUCT_CANDIDATES_FILE

def show(path, title, n=80):
    path = Path(path)
    print(f"\n--- {title} ---")
    if not path.exists():
        print(f"Missing: {path}")
        return
    df = pd.read_csv(path)
    print(f"Rows: {len(df)}")
    if len(df):
        cols = [c for c in [
            "set_name",
            "box_name",
            "tcgcsv_group_id",
            "tcgplayer_product_id",
            "approved_tcgplayer_product_id",
            "official_product_name",
            "approved_product_name",
            "market_price",
            "candidate_score",
            "candidate_rank",
            "case_or_pack_flag",
            "high_price_flag",
            "approval_status",
            "approval_method",
            "notes",
        ] if c in df.columns]
        print(df[cols].head(n).to_string(index=False))

def main():
    show(PRODUCT_MASTER_FILE, "Product Master")
    show(PRODUCT_SELECTION_REVIEW_FILE, "Selection Review")
    show(PRODUCT_CANDIDATES_FILE, "All Product Candidates")

if __name__ == "__main__":
    main()
