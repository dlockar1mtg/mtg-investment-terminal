from pathlib import Path
import sys
import pandas as pd

from config import PRODUCT_MASTER_FILE

def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("python approve_product.py <tcgcsv_group_id> <tcgplayer_product_id>")
        print("")
        print("Example:")
        print("python approve_product.py 23019 484912")
        return

    group_id = str(sys.argv[1])
    product_id = str(sys.argv[2])

    path = Path(PRODUCT_MASTER_FILE)
    if not path.exists():
        print(f"Product master not found: {path}")
        return

    df = pd.read_csv(path, dtype=str)
    mask = df["tcgcsv_group_id"].astype(str) == group_id

    if not mask.any():
        print(f"No product master row found for group {group_id}. Run python run.py first to generate candidates.")
        return

    df.loc[mask, "approved_tcgplayer_product_id"] = product_id
    df.loc[mask, "approval_status"] = "approved"
    df.loc[mask, "approval_method"] = "manual_user_approved"
    df.loc[mask, "notes"] = df.loc[mask, "notes"].fillna("") + f"; manually approved product_id={product_id}"

    path.write_text(df.to_csv(index=False), encoding="utf-8")
    print(f"Approved group {group_id} -> product {product_id}")
    print("Now run:")
    print("python reset_source_cache.py")
    print("python run.py")

if __name__ == "__main__":
    main()
