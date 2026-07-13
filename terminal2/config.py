from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT_DIR / "data"
TERMINAL2_DIR = DATA_DIR / "terminal2"
DB_FILE = TERMINAL2_DIR / "mtg_investment_terminal.sqlite"

PRODUCT_MASTER_FILE = DATA_DIR / "product_master" / "investment_products.csv"

ARCHIVE_CACHE_DIR = TERMINAL2_DIR / "archive_cache"
ARCHIVE_EXTRACT_DIR = TERMINAL2_DIR / "extracted_archives"
AUDIT_DIR = TERMINAL2_DIR / "audit"
EXPORT_DIR = TERMINAL2_DIR / "exports"

TCGCSV_ARCHIVE_BASE_URL = "https://tcgcsv.com/archive/tcgplayer"
TCGCSV_ARCHIVE_START_DATE = "2024-02-08"

USER_AGENT = "MTGInvestmentTerminal/2.0 (historical archive backfill; personal use)"
DEFAULT_MONTHLY_START = "2024-02-08"

# Module 1 — Data Foundation
METADATA_FILE = TERMINAL2_DIR / "product_metadata.csv"
METADATA_TEMPLATE_FILE = TERMINAL2_DIR / "product_metadata_template.csv"
PORTFOLIO_HOLDINGS_FILE = TERMINAL2_DIR / "portfolio_holdings.csv"
PORTFOLIO_HOLDINGS_TEMPLATE_FILE = TERMINAL2_DIR / "portfolio_holdings_template.csv"
DISCOVERY_CANDIDATES_FILE = TERMINAL2_DIR / "product_discovery_candidates.csv"
DISCOVERY_AUDIT_FILE = AUDIT_DIR / "product_discovery_audit.csv"
DAILY_UPDATE_AUDIT_FILE = AUDIT_DIR / "daily_update_audit.csv"
SUPPORTED_PRODUCT_TYPES = [
    "Collector Booster Display",
    "Draft Booster Display",
    "Traditional Booster Display",
    "Masters Booster Display",
    "Secret Lair Drop",
]
EXCLUDED_PRODUCT_TYPES = ["Play Booster Display", "Set Booster Display"]
