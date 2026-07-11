from models.historical_importer import create_historical_import_template
from config import HISTORICAL_IMPORT_TEMPLATE_FILE

def main():
    df = create_historical_import_template()
    print(f"Template created: {HISTORICAL_IMPORT_TEMPLATE_FILE}")
    print(f"Rows: {len(df)}")

if __name__ == "__main__":
    main()
