from pathlib import Path
import pandas as pd

from config import (
    DAILY_PRICE_OBSERVATIONS_FILE,
    ROLLING_PRICE_METRICS_FILE,
    REAL_SIGNAL_OUTPUT_FILE,
    PRODUCT_MASTER_MODEL_INPUT_FILE,
    MARKET_INTELLIGENCE_FILE,
    MONTE_CARLO_OUTPUT_FILE,
    SOURCE_CACHE_DIR,
)

FILES = [
    ("Daily price observations", DAILY_PRICE_OBSERVATIONS_FILE),
    ("Rolling price metrics", ROLLING_PRICE_METRICS_FILE),
    ("Real signal scores", REAL_SIGNAL_OUTPUT_FILE),
    ("Product master model input", PRODUCT_MASTER_MODEL_INPUT_FILE),
    ("Market intelligence", MARKET_INTELLIGENCE_FILE),
    ("Monte Carlo summary", MONTE_CARLO_OUTPUT_FILE),
    ("Latest price cache", Path(SOURCE_CACHE_DIR) / "latest_prices.csv"),
]

def main():
    print("\nV12.1 Pipeline Validation\n")

    all_ok = True
    for label, path in FILES:
        path = Path(path)
        if not path.exists():
            print(f"FAIL: {label} missing -> {path}")
            all_ok = False
            continue

        try:
            df = pd.read_csv(path)
            rows = len(df)
        except Exception as exc:
            print(f"FAIL: {label} unreadable -> {path} ({exc})")
            all_ok = False
            continue

        if rows == 0:
            print(f"WARN: {label} exists but has 0 rows -> {path}")
        else:
            print(f"OK: {label} rows={rows} -> {path}")

    if all_ok:
        print("\nValidation finished. Required files exist.")
    else:
        print("\nValidation found missing/unreadable files.")

if __name__ == "__main__":
    main()
