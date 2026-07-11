from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DASHBOARD = DATA / "dashboard"
ANALYTICS = DATA / "analytics"

REQUIRED_FILES = [
    DASHBOARD / "dataset_manifest.csv",
    DASHBOARD / "data_dictionary.csv",
    DASHBOARD / "warehouse_status.json",
    DASHBOARD / "products" / "product_summary.csv",
    DASHBOARD / "products" / "historical_prices.csv",
    DASHBOARD / "products" / "product_rankings.csv",
    DASHBOARD / "market" / "magic_market_index.csv",
    DASHBOARD / "lifecycle" / "lifecycle_stage.csv",
    DASHBOARD / "seasonality" / "seasonality_month.csv",
    DASHBOARD / "executive" / "dashboard_summary.csv",
    DASHBOARD / "executive" / "top_opportunities.csv",
    ANALYTICS / "current" / "product_summary.csv",
    ANALYTICS / "current" / "rankings.csv",
]

def main():
    print("\nDashboard Warehouse Validation\n")
    failures = 0

    for path in REQUIRED_FILES:
        if not path.exists():
            print(f"FAIL: Missing {path.relative_to(ROOT)}")
            failures += 1
            continue

        if path.suffix == ".csv":
            try:
                df = pd.read_csv(path)
                print(f"OK: {path.relative_to(ROOT)} rows={len(df)} columns={len(df.columns)}")
            except Exception as exc:
                print(f"FAIL: Could not read {path.relative_to(ROOT)}: {exc}")
                failures += 1
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
                print(f"OK: {path.relative_to(ROOT)}")
            except Exception as exc:
                print(f"FAIL: Could not parse {path.relative_to(ROOT)}: {exc}")
                failures += 1

    history_root = ANALYTICS / "history"
    dated_folders = [p for p in history_root.iterdir() if p.is_dir()] if history_root.exists() else []
    if dated_folders:
        print(f"OK: Historical snapshot folders={len(dated_folders)}")
    else:
        print("FAIL: No historical snapshot folder found.")
        failures += 1

    if failures:
        print(f"\nValidation completed with {failures} failure(s).")
        raise SystemExit(1)

    print("\nValidation passed.")

if __name__ == "__main__":
    main()
