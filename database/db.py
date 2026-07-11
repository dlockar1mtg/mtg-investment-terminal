from __future__ import annotations

from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import pandas as pd

from config import DATABASE_FILE

SCHEMA = '''
CREATE TABLE IF NOT EXISTS product_mapping (
    box_name TEXT PRIMARY KEY,
    tcgplayer_product_id TEXT,
    tcgcsv_category_id TEXT,
    tcgcsv_group_id TEXT,
    source_product_name TEXT,
    source_url TEXT,
    verified TEXT,
    notes TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    box_name TEXT NOT NULL,
    tcgplayer_product_id TEXT,
    source_name TEXT NOT NULL,
    market_price REAL,
    low_price REAL,
    mid_price REAL,
    high_price REAL,
    direct_low_price REAL,
    sub_type_name TEXT,
    source_timestamp TEXT,
    collected_at TEXT NOT NULL,
    price_data_quality INTEGER,
    raw_payload TEXT
);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    rows_collected INTEGER DEFAULT 0,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_box_time
ON price_snapshots(box_name, collected_at);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_product
ON price_snapshots(tcgplayer_product_id);
'''

def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def get_connection(db_path=DATABASE_FILE):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)

def init_db(db_path=DATABASE_FILE):
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()

def upsert_product_mapping(df, db_path=DATABASE_FILE):
    if df is None or df.empty:
        return
    init_db(db_path)
    now = now_utc()
    cols = [
        "box_name",
        "tcgplayer_product_id",
        "tcgcsv_category_id",
        "tcgcsv_group_id",
        "source_product_name",
        "source_url",
        "verified",
        "notes",
    ]
    working = df.copy()
    for col in cols:
        if col not in working.columns:
            working[col] = None
    working["updated_at"] = now
    rows = working[cols + ["updated_at"]].to_dict("records")
    with get_connection(db_path) as conn:
        for r in rows:
            conn.execute(
                '''
                INSERT INTO product_mapping
                (box_name, tcgplayer_product_id, tcgcsv_category_id, tcgcsv_group_id,
                 source_product_name, source_url, verified, notes, updated_at)
                VALUES (:box_name, :tcgplayer_product_id, :tcgcsv_category_id, :tcgcsv_group_id,
                        :source_product_name, :source_url, :verified, :notes, :updated_at)
                ON CONFLICT(box_name) DO UPDATE SET
                    tcgplayer_product_id=excluded.tcgplayer_product_id,
                    tcgcsv_category_id=excluded.tcgcsv_category_id,
                    tcgcsv_group_id=excluded.tcgcsv_group_id,
                    source_product_name=excluded.source_product_name,
                    source_url=excluded.source_url,
                    verified=excluded.verified,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                ''',
                r,
            )
        conn.commit()

def insert_price_snapshots(df, db_path=DATABASE_FILE):
    if df is None or df.empty:
        return 0
    init_db(db_path)
    cols = [
        "box_name",
        "tcgplayer_product_id",
        "source_name",
        "market_price",
        "low_price",
        "mid_price",
        "high_price",
        "direct_low_price",
        "sub_type_name",
        "source_timestamp",
        "collected_at",
        "price_data_quality",
        "raw_payload",
    ]
    working = df.copy()
    for col in cols:
        if col not in working.columns:
            working[col] = None
    with get_connection(db_path) as conn:
        working[cols].to_sql("price_snapshots", conn, if_exists="append", index=False)
    return len(working)

def latest_prices(db_path=DATABASE_FILE):
    init_db(db_path)
    query = '''
    WITH ranked AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY box_name
                ORDER BY
                    CASE source_name
                        WHEN 'tcgplayer_api' THEN 1
                        WHEN 'tcgcsv' THEN 2
                        WHEN 'manual_verified' THEN 3
                        WHEN 'manual_seed' THEN 4
                        ELSE 5
                    END,
                    collected_at DESC
            ) AS rn
        FROM price_snapshots
        WHERE market_price IS NOT NULL
    )
    SELECT
        box_name,
        tcgplayer_product_id,
        source_name AS price_source,
        market_price,
        low_price,
        collected_at AS last_price_checked,
        price_data_quality
    FROM ranked
    WHERE rn = 1
    '''
    with get_connection(db_path) as conn:
        return pd.read_sql_query(query, conn)

def log_source_run(source_name, status, started_at, finished_at=None, rows_collected=0, message="", db_path=DATABASE_FILE):
    init_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            '''
            INSERT INTO source_runs
            (source_name, status, started_at, finished_at, rows_collected, message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (source_name, status, started_at, finished_at, rows_collected, message),
        )
        conn.commit()
