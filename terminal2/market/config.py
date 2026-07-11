from pathlib import Path
from terminal2.config import ROOT_DIR

DATA_DIR = Path(ROOT_DIR) / "data"
TERMINAL2_DIR = DATA_DIR / "terminal2"

MARKET_INPUT_DIR = TERMINAL2_DIR / "market_inputs"
MARKET_AUDIT_DIR = TERMINAL2_DIR / "market_audit"

SUPPLY_INPUT_FILE = MARKET_INPUT_DIR / "supply_observations.csv"
SALES_INPUT_FILE = MARKET_INPUT_DIR / "sales_observations.csv"
SOURCE_HEALTH_EXPORT = DATA_DIR / "dashboard" / "market" / "source_health.csv"
MARKET_HEALTH_EXPORT = DATA_DIR / "dashboard" / "market" / "market_health.csv"
MARKET_INTELLIGENCE_EXPORT = DATA_DIR / "dashboard" / "market" / "market_intelligence.csv"
MARKET_SIGNALS_EXPORT = DATA_DIR / "dashboard" / "market" / "market_signals.csv"
