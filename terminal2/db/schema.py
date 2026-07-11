from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal2.config import DB_FILE


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS products (
    investment_product_id TEXT PRIMARY KEY,
    set_name TEXT,
    box_name TEXT,
    tcgplayer_product_id TEXT,
    tcgcsv_category_id TEXT,
    tcgcsv_group_id TEXT,
    product_type TEXT,
    approval_status TEXT,
    approval_method TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_date TEXT NOT NULL,
    investment_product_id TEXT NOT NULL,
    tcgplayer_product_id TEXT,
    price_source TEXT NOT NULL,
    market_price REAL,
    low_price REAL,
    mid_price REAL,
    high_price REAL,
    price_data_quality REAL,
    source_run_id TEXT,
    raw_payload TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(observation_date, investment_product_id, price_source),
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);

CREATE TABLE IF NOT EXISTS source_runs (
    source_run_id TEXT PRIMARY KEY,
    source_name TEXT,
    run_started_at TEXT,
    run_finished_at TEXT,
    status TEXT,
    records_processed INTEGER,
    message TEXT
);

CREATE TABLE IF NOT EXISTS product_features (
    investment_product_id TEXT PRIMARY KEY,
    latest_price REAL,
    observation_count INTEGER,
    first_observation_date TEXT,
    latest_observation_date TEXT,
    ath_price REAL,
    atl_price REAL,
    drawdown_from_ath REAL,
    return_30d REAL,
    return_90d REAL,
    return_180d REAL,
    return_365d REAL,
    ma_30d REAL,
    ma_90d REAL,
    annualized_volatility REAL,
    trend_score REAL,
    volatility_score REAL,
    history_confidence REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);

CREATE TABLE IF NOT EXISTS investment_scores (
    investment_product_id TEXT PRIMARY KEY,
    current_price REAL,
    investment_score REAL,
    risk_adjusted_score REAL,
    rating TEXT,
    buy_signal TEXT,
    target_buy_price REAL,
    expected_cagr REAL,
    projection_confidence REAL,
    mc_median_5yr REAL,
    mc_p05_5yr REAL,
    mc_p95_5yr REAL,
    prob_double REAL,
    prob_loss REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);

CREATE INDEX IF NOT EXISTS idx_price_obs_product_date
ON price_observations(investment_product_id, observation_date);

CREATE INDEX IF NOT EXISTS idx_price_obs_date
ON price_observations(observation_date);
"""


def get_connection(db_file: Path = DB_FILE) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_file: Path = DB_FILE):
    conn = get_connection(db_file)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized {DB_FILE}")
