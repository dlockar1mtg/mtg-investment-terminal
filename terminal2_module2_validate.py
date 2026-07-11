from pathlib import Path
import sqlite3
import pandas as pd

from terminal2.config import DB_FILE, ROOT_DIR

ROOT = Path(ROOT_DIR)
DATA = ROOT / "data"

REQUIRED_TABLES = [
    "supply_observations",
    "sales_observations",
    "market_intelligence",
    "market_health_history",
    "source_health_history",
]

REQUIRED_FILES = [
    DATA / "dashboard" / "market" / "market_health.csv",
    DATA / "dashboard" / "market" / "market_intelligence.csv",
    DATA / "dashboard" / "market" / "market_signals.csv",
    DATA / "dashboard" / "market" / "source_health.csv",
    DATA / "dashboard" / "market" / "supply_metrics.csv",
    DATA / "dashboard" / "market" / "liquidity.csv",
    DATA / "dashboard" / "executive" / "market_health_summary.csv",
    DATA / "analytics" / "current" / "market_intelligence.csv",
    DATA / "analytics" / "current" / "market_health.csv",
]

def main():
    failures = 0
    print("\nModule 2 Validation\n")

    connection = sqlite3.connect(DB_FILE)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()

    for table in REQUIRED_TABLES:
        if table in tables:
            print(f"OK table: {table}")
        else:
            print(f"FAIL table missing: {table}")
            failures += 1

    for path in REQUIRED_FILES:
        if not path.exists():
            print(f"FAIL file missing: {path.relative_to(ROOT)}")
            failures += 1
            continue
        try:
            df = pd.read_csv(path)
            print(f"OK file: {path.relative_to(ROOT)} rows={len(df)} columns={len(df.columns)}")
        except Exception as exc:
            print(f"FAIL unreadable: {path.relative_to(ROOT)} ({exc})")
            failures += 1

    intelligence = pd.read_csv(DATA / "dashboard" / "market" / "market_intelligence.csv")
    if len(intelligence) == 0:
        print("FAIL: market_intelligence.csv has zero rows")
        failures += 1
    else:
        print(f"OK: market intelligence covers {intelligence['investment_product_id'].nunique()} products")

    if failures:
        print(f"\nValidation completed with {failures} failure(s).")
        raise SystemExit(1)

    print("\nModule 2 validation passed.")

if __name__ == "__main__":
    main()
