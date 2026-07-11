from __future__ import annotations
from terminal2.db.schema import get_connection, init_db

PRODUCT_COLUMNS = {
    "asset_class": "TEXT",
    "release_date": "TEXT",
    "release_year": "INTEGER",
    "era": "TEXT",
    "franchise": "TEXT",
    "universes_beyond": "INTEGER DEFAULT 0",
    "masters_product": "INTEGER DEFAULT 0",
    "secret_lair": "INTEGER DEFAULT 0",
    "foil_variant": "TEXT",
    "language": "TEXT DEFAULT 'English'",
}

METADATA_SQL = """
CREATE TABLE IF NOT EXISTS product_metadata (
    investment_product_id TEXT PRIMARY KEY,
    release_date TEXT,
    msrp REAL,
    print_status TEXT,
    print_window_months REAL,
    months_out_of_print REAL,
    franchise TEXT,
    ip_strength_score REAL,
    serialized_cards INTEGER,
    premium_treatment_score REAL,
    reprint_risk_score REAL,
    commander_demand_score REAL,
    competitive_demand_score REAL,
    collector_demand_score REAL,
    supply_class TEXT,
    source TEXT,
    confidence REAL,
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(investment_product_id) REFERENCES products(investment_product_id)
);
"""


def migrate_module1():
    init_db()
    connection = get_connection()
    try:
        existing = {row[1] for row in connection.execute("PRAGMA table_info(products)")}
        for column, sql_type in PRODUCT_COLUMNS.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE products ADD COLUMN {column} {sql_type}")
        connection.executescript(METADATA_SQL)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_products_type ON products(product_type)")
        connection.commit()
    finally:
        connection.close()
