from __future__ import annotations

from terminal2.db.module1_migration import migrate_module1
from terminal2.db.schema import get_connection


MODULE2_SQL = """
CREATE TABLE IF NOT EXISTS supply_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_date TEXT NOT NULL,
    investment_product_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    listing_count REAL,
    seller_count REAL,
    inventory_units REAL,
    inventory_change_7d REAL,
    inventory_change_30d REAL,
    source_confidence REAL,
    raw_payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(observation_date, investment_product_id, source_name),
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);

CREATE TABLE IF NOT EXISTS sales_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_date TEXT NOT NULL,
    investment_product_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    sales_7d REAL,
    sales_30d REAL,
    median_sold_price_30d REAL,
    sell_through_rate_30d REAL,
    average_days_to_sale REAL,
    source_confidence REAL,
    raw_payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(observation_date, investment_product_id, source_name),
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);

CREATE TABLE IF NOT EXISTS market_intelligence (
    investment_product_id TEXT PRIMARY KEY,
    observation_date TEXT,
    current_price REAL,
    spread_pct REAL,
    price_freshness_hours REAL,
    supply_signal_score REAL,
    supply_confidence REAL,
    liquidity_score REAL,
    liquidity_confidence REAL,
    sales_velocity_score REAL,
    sales_confidence REAL,
    market_relative_strength REAL,
    market_alpha_30d REAL,
    market_alpha_90d REAL,
    market_intelligence_score REAL,
    market_intelligence_confidence REAL,
    signal_basis TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);

CREATE TABLE IF NOT EXISTS market_health_history (
    snapshot_date TEXT PRIMARY KEY,
    generated_at_utc TEXT,
    total_products INTEGER,
    products_with_current_price INTEGER,
    products_updated_today INTEGER,
    average_return_30d REAL,
    average_return_90d REAL,
    median_return_30d REAL,
    average_volatility REAL,
    buy_signal_count INTEGER,
    watch_signal_count INTEGER,
    wait_signal_count INTEGER,
    avoid_signal_count INTEGER,
    below_target_count INTEGER,
    at_ath_count INTEGER,
    near_atl_count INTEGER,
    average_confidence REAL,
    average_data_quality REAL,
    average_market_intelligence REAL,
    market_index_level REAL,
    market_breadth_positive_pct REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS source_health_history (
    snapshot_date TEXT NOT NULL,
    source_name TEXT NOT NULL,
    latest_success_at TEXT,
    latest_failure_at TEXT,
    success_runs INTEGER,
    failed_runs INTEGER,
    success_rate REAL,
    records_processed INTEGER,
    average_price_age_hours REAL,
    products_covered INTEGER,
    coverage_pct REAL,
    source_health_score REAL,
    status TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(snapshot_date, source_name)
);

CREATE INDEX IF NOT EXISTS idx_supply_product_date
ON supply_observations(investment_product_id, observation_date);

CREATE INDEX IF NOT EXISTS idx_sales_product_date
ON sales_observations(investment_product_id, observation_date);

CREATE INDEX IF NOT EXISTS idx_market_intelligence_score
ON market_intelligence(market_intelligence_score DESC);
"""


def migrate_module2():
    migrate_module1()
    connection = get_connection()
    try:
        connection.executescript(MODULE2_SQL)
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    migrate_module2()
    print("Module 2 database migration complete.")
