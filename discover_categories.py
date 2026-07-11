from collectors.common import safe_get_json
from config import TCGCSV_BASE_URL

def main():
    url = f"{TCGCSV_BASE_URL}/categories"
    payload = safe_get_json(url, timeout=90, source_name="tcgcsv_categories_debug")
    results = payload.get("results", []) if isinstance(payload, dict) else payload
    for item in results:
        name = item.get("name")
        display = item.get("displayName")
        seo = item.get("seoCategoryName")
        cid = item.get("categoryId") or item.get("category_id")
        print(f"{cid}: name={name} | display={display} | seo={seo}")

if __name__ == "__main__":
    main()
