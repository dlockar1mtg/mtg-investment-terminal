from collectors.tcgcsv_discovery import fetch_categories, detect_magic_category_id
from config import TCGCSV_BASE_URL, SOURCE_REQUEST_LOG_FILE

def main():
    print("TCGCSV_BASE_URL:", TCGCSV_BASE_URL)
    print("Request log:", SOURCE_REQUEST_LOG_FILE)

    categories = fetch_categories()
    print("\nFirst 20 categories:")
    cols = [c for c in ["categoryId", "name", "displayName", "seoCategoryName"] if c in categories.columns]
    print(categories[cols].head(20).to_string(index=False))

    print("\nDetected Magic category:")
    print(detect_magic_category_id())

if __name__ == "__main__":
    main()
