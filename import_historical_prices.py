from models.historical_importer import import_historical_prices
from config import HISTORICAL_IMPORT_FILE, HISTORICAL_IMPORT_AUDIT_FILE, ROLLING_PRICE_METRICS_FILE

def main():
    result = import_historical_prices()
    audit = result["audit"]
    print("\nHistorical import complete.")
    print(audit.to_string(index=False))
    print(f"\nAudit: {HISTORICAL_IMPORT_AUDIT_FILE}")
    print(f"Rolling metrics: {ROLLING_PRICE_METRICS_FILE}")

if __name__ == "__main__":
    main()
