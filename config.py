from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parent

INPUT_FILE = ROOT_DIR / "data" / "input" / "collector_booster_boxes.csv"
PRODUCT_MAP_FILE = ROOT_DIR / "data" / "reference" / "product_map.csv"
SOURCE_CACHE_DIR = ROOT_DIR / "data" / "source_cache"
REFERENCE_DIR = ROOT_DIR / "data" / "reference"
HISTORY_DIR = ROOT_DIR / "data" / "history"
PORTFOLIO_DIR = ROOT_DIR / "data" / "portfolio"
OUTPUT_DIR = ROOT_DIR / "outputs"
RAW_DATA_DIR = ROOT_DIR / "data" / "raw"
DATABASE_FILE = ROOT_DIR / "data" / "database" / "mtg_prices.sqlite"

PORTFOLIO_BUDGET = 5000

MIN_PORTFOLIO_RISK_ADJUSTED_SCORE = 74
MIN_PORTFOLIO_EXPECTED_CAGR = 0.08
ALLOW_SPECULATIVE_IN_PORTFOLIO = False
MAX_QUANTITY_PER_BOX = 4
MAX_ALLOCATION_PER_BOX = 0.45

MIN_EXPECTED_CAGR = -0.05
MAX_BASE_CAGR = 0.24
MAX_BULL_CAGR = 0.32

REFRESH_SOURCE_DATA = True
ALLOW_STALE_PRICE_FALLBACK = True
MAX_PRICE_AGE_HOURS = 24
MIN_PRICE_DATA_QUALITY = 70

SAVE_DAILY_SNAPSHOT = True

# Source-layer controls
AUTO_UPDATE_PRICES_BEFORE_RUN = True
USE_TCGCSV = True
USE_TCGPLAYER_API = False
USE_MTGJSON = True
USE_SCRYFALL = True

# TCGplayer API credentials are optional and only work if you already have access.
TCGPLAYER_PUBLIC_KEY = os.getenv("TCGPLAYER_PUBLIC_KEY", "")
TCGPLAYER_PRIVATE_KEY = os.getenv("TCGPLAYER_PRIVATE_KEY", "")
TCGPLAYER_ACCESS_TOKEN = os.getenv("TCGPLAYER_ACCESS_TOKEN", "")

# TCGCSV public endpoint settings
TCGCSV_BASE_URL = "https://tcgcsv.com/tcgplayer"

# Scryfall/MTGJSON public endpoints
SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
MTGJSON_ALL_PRINTINGS_URL = "https://mtgjson.com/api/v5/AllPrintings.json"
MTGJSON_ALL_SETS_URL = "https://mtgjson.com/api/v5/SetList.json"


# v5.1 Discovery mode
DISCOVER_ALL_COLLECTOR_BOXES = True
DISCOVERED_PRODUCTS_FILE = ROOT_DIR / "data" / "discovered" / "collector_booster_boxes_discovered.csv"
DISCOVERED_MODEL_INPUT_FILE = ROOT_DIR / "data" / "discovered" / "collector_booster_model_input.csv"

# TCGCSV category for Magic: The Gathering.
# TCGCSV docs sometimes use examples from Pokemon; category IDs should be verified at runtime.
TCGCSV_MAGIC_CATEGORY_ID = None

# Discovery filters
COLLECTOR_BOX_INCLUDE_TERMS = [
    "collector booster display",
    "collector booster box",
    "collector boosters display",
    "collector booster case",
]
COLLECTOR_BOX_EXCLUDE_TERMS = [
    "pack",
    "sample",
    "blister",
    "bundle",
    "commander deck",
    "starter kit",
    "draft booster",
    "set booster",
    "play booster",
    "jumpstart",
    "theme booster",
    "prerelease",
]


# v6 source-layer settings
AUTO_DETECT_TCGCSV_MAGIC_CATEGORY = True
TCGCSV_CATEGORY_NAME_MATCHES = ["magic", "magic: the gathering"]
TCGCSV_REQUEST_DELAY_SECONDS = 0.15
TCGCSV_MAX_GROUPS = None  # Set to a number like 25 for quick testing.
SOURCE_REQUEST_LOG_FILE = ROOT_DIR / "data" / "logs" / "source_requests.csv"
DISCOVERY_SUMMARY_FILE = ROOT_DIR / "outputs" / "discovery_summary.csv"


# v8 consensus pricing
USE_MARKET_CONSENSUS = True
MANUAL_PRICE_SOURCES_FILE = ROOT_DIR / "data" / "reference" / "manual_price_sources.csv"
CONSENSUS_PRICE_FILE = ROOT_DIR / "data" / "source_cache" / "consensus_prices.csv"
OUTLIER_RATIO_THRESHOLD = 1.75
MIN_CONSENSUS_SOURCES = 1


# v9 product-master settings
USE_PRODUCT_MASTER = True
PRODUCT_MASTER_FILE = ROOT_DIR / "data" / "product_master" / "investment_products.csv"
PRODUCT_CANDIDATES_FILE = ROOT_DIR / "data" / "product_master" / "product_candidates.csv"
PRODUCT_SELECTION_REVIEW_FILE = ROOT_DIR / "data" / "product_master" / "product_selection_review.csv"
PRODUCT_MASTER_MODEL_INPUT_FILE = ROOT_DIR / "data" / "product_master" / "product_master_model_input.csv"
AUTO_APPROVE_HIGH_CONFIDENCE_PRODUCTS = True
PRODUCT_MASTER_MIN_SELECTION_SCORE = 180


# v10 investment database settings
USE_INVESTMENT_FEATURES = True
INVESTMENT_FEATURES_FILE = ROOT_DIR / "data" / "investment" / "investment_features.csv"
HISTORICAL_METRICS_FILE = ROOT_DIR / "data" / "investment" / "historical_metrics.csv"
INVESTMENT_MODEL_INPUT_FILE = ROOT_DIR / "data" / "investment" / "investment_model_input.csv"
RELEASE_METADATA_FILE = ROOT_DIR / "data" / "reference" / "release_metadata.csv"


# v11 market intelligence settings
USE_MARKET_INTELLIGENCE = True
MARKET_INTELLIGENCE_FILE = ROOT_DIR / "data" / "market_intelligence" / "market_intelligence.csv"
MONTE_CARLO_OUTPUT_FILE = ROOT_DIR / "data" / "monte_carlo" / "monte_carlo_summary.csv"
MONTE_CARLO_SIMULATIONS = 5000
MONTE_CARLO_YEARS = 5
MONTE_CARLO_RANDOM_SEED = 42
MARKET_INTELLIGENCE_MODEL_INPUT_FILE = ROOT_DIR / "data" / "market_intelligence" / "market_intelligence_model_input.csv"


# v12 real-signal market database settings
USE_REAL_SIGNAL_ENGINE = True
MARKET_DATABASE_DIR = ROOT_DIR / "data" / "market_database"
DAILY_PRICE_OBSERVATIONS_FILE = MARKET_DATABASE_DIR / "daily_price_observations.csv"
ROLLING_PRICE_METRICS_FILE = ROOT_DIR / "data" / "rolling_metrics" / "rolling_price_metrics.csv"
INVENTORY_SIGNALS_FILE = ROOT_DIR / "data" / "market_inputs" / "inventory_signals.csv"
SALES_VELOCITY_FILE = ROOT_DIR / "data" / "market_inputs" / "sales_velocity.csv"
DEMAND_SIGNALS_FILE = ROOT_DIR / "data" / "market_inputs" / "demand_signals.csv"
SCARCITY_SIGNALS_FILE = ROOT_DIR / "data" / "market_inputs" / "scarcity_signals.csv"
REAL_SIGNAL_OUTPUT_FILE = ROOT_DIR / "data" / "market_signals" / "real_signal_scores.csv"
REAL_SIGNAL_MODEL_INPUT_FILE = ROOT_DIR / "data" / "market_signals" / "real_signal_model_input.csv"


# v13 historical importer settings
HISTORICAL_IMPORT_TEMPLATE_FILE = ROOT_DIR / "data" / "historical_imports" / "historical_price_import_template.csv"
HISTORICAL_IMPORT_FILE = ROOT_DIR / "data" / "historical_imports" / "historical_price_import.csv"
HISTORICAL_IMPORT_AUDIT_FILE = ROOT_DIR / "data" / "historical_imports" / "historical_import_audit.csv"


# v13.1 TCGCSV monthly archive backfill
TCGCSV_ARCHIVE_START_DATE = "2024-02-08"
TCGCSV_ARCHIVE_DIR = ROOT_DIR / "data" / "historical_imports" / "tcgcsv_archives"
TCGCSV_ARCHIVE_EXTRACT_DIR = ROOT_DIR / "data" / "historical_imports" / "tcgcsv_extracted"
TCGCSV_MONTHLY_BACKFILL_AUDIT_FILE = ROOT_DIR / "data" / "historical_imports" / "audit" / "tcgcsv_monthly_backfill_audit.csv"
TCGCSV_ARCHIVE_BASE_URL = "https://tcgcsv.com/archive/tcgplayer"
