from pathlib import Path
from terminal2.config import ROOT_DIR
MASTER_ROOT=Path(ROOT_DIR)/"data"/"terminal2"/"master_secret_lair"
RAW_ROOT=MASTER_ROOT/"raw"
CACHE_ROOT=MASTER_ROOT/"cache"
MASTER_PRODUCTS_PATH=MASTER_ROOT/"master_secret_lair_products.csv"
MASTER_HISTORY_PATH=MASTER_ROOT/"master_secret_lair_price_history.csv"
PRODUCT_MAP_PATH=MASTER_ROOT/"master_secret_lair_product_map.csv"
OFFICIAL_URLS=(
 "https://secretlair.wizards.com/us/en/shopall",
 "https://secretlair.wizards.com/us/en/past-sales",
)
SCRYFALL_BULK_INDEX_URL="https://api.scryfall.com/bulk-data"
TCGCSV_BASE_URL="https://tcgcsv.com/tcgplayer"
REQUEST_TIMEOUT=90
REQUEST_DELAY_SECONDS=0.15
