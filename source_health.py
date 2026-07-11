from __future__ import annotations

import sqlite3
import pandas as pd
from config import DATABASE_FILE, SOURCE_CACHE_DIR

def main():
    print("\nSource Cache:")
    cache_file = SOURCE_CACHE_DIR / "latest_prices.csv"
    if cache_file.exists():
        print(pd.read_csv(cache_file).to_string(index=False))
    else:
        print("No latest_prices.csv found.")

    print("\nSQLite Source Runs:")
    if not DATABASE_FILE.exists():
        print("Database does not exist yet.")
        return

    with sqlite3.connect(DATABASE_FILE) as conn:
        try:
            runs = pd.read_sql_query("SELECT * FROM source_runs ORDER BY id DESC LIMIT 20", conn)
            print(runs.to_string(index=False))
        except Exception as exc:
            print(f"Could not read source_runs: {exc}")

        try:
            latest = pd.read_sql_query(
                '''
                SELECT box_name, source_name, market_price, low_price, collected_at, price_data_quality
                FROM price_snapshots
                ORDER BY collected_at DESC
                LIMIT 50
                ''',
                conn,
            )
            print("\nLatest Price Snapshots:")
            print(latest.to_string(index=False))
        except Exception as exc:
            print(f"Could not read price_snapshots: {exc}")

if __name__ == "__main__":
    main()
