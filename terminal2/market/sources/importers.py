from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from terminal2.db.module2_migration import migrate_module2
from terminal2.db.schema import get_connection
from terminal2.market.config import SUPPLY_INPUT_FILE, SALES_INPUT_FILE


def _clean_numeric(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def import_supply_observations(path=SUPPLY_INPUT_FILE):
    migrate_module2()
    path = Path(path)
    if not path.exists():
        return {"rows_read": 0, "rows_imported": 0, "message": f"Missing {path}"}

    df = pd.read_csv(path, dtype={"investment_product_id": str})
    if df.empty:
        return {"rows_read": 0, "rows_imported": 0, "message": "Supply input is empty."}

    required = ["observation_date", "investment_product_id", "source_name"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Supply input missing columns: {missing}")

    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce").dt.date.astype(str)
    df = _clean_numeric(df, [
        "listing_count", "seller_count", "inventory_units",
        "inventory_change_7d", "inventory_change_30d", "source_confidence",
    ])
    valid_metric = df[[
        c for c in ["listing_count", "seller_count", "inventory_units", "inventory_change_7d", "inventory_change_30d"]
        if c in df.columns
    ]].notna().any(axis=1)
    df = df[df["investment_product_id"].notna() & valid_metric].copy()

    connection = get_connection()
    imported = 0
    try:
        for _, row in df.iterrows():
            connection.execute(
                """
                INSERT INTO supply_observations (
                    observation_date, investment_product_id, source_name,
                    listing_count, seller_count, inventory_units,
                    inventory_change_7d, inventory_change_30d,
                    source_confidence, raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_date, investment_product_id, source_name) DO UPDATE SET
                    listing_count=excluded.listing_count,
                    seller_count=excluded.seller_count,
                    inventory_units=excluded.inventory_units,
                    inventory_change_7d=excluded.inventory_change_7d,
                    inventory_change_30d=excluded.inventory_change_30d,
                    source_confidence=excluded.source_confidence,
                    raw_payload=excluded.raw_payload,
                    created_at=CURRENT_TIMESTAMP
                """,
                (
                    row.get("observation_date"),
                    row.get("investment_product_id"),
                    row.get("source_name") or "manual_or_external",
                    row.get("listing_count"),
                    row.get("seller_count"),
                    row.get("inventory_units"),
                    row.get("inventory_change_7d"),
                    row.get("inventory_change_30d"),
                    row.get("source_confidence"),
                    json.dumps(row.dropna().to_dict(), default=str),
                ),
            )
            imported += 1
        connection.commit()
    finally:
        connection.close()

    return {"rows_read": len(pd.read_csv(path)), "rows_imported": imported, "message": "OK"}


def import_sales_observations(path=SALES_INPUT_FILE):
    migrate_module2()
    path = Path(path)
    if not path.exists():
        return {"rows_read": 0, "rows_imported": 0, "message": f"Missing {path}"}

    df = pd.read_csv(path, dtype={"investment_product_id": str})
    if df.empty:
        return {"rows_read": 0, "rows_imported": 0, "message": "Sales input is empty."}

    required = ["observation_date", "investment_product_id", "source_name"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Sales input missing columns: {missing}")

    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce").dt.date.astype(str)
    df = _clean_numeric(df, [
        "sales_7d", "sales_30d", "median_sold_price_30d",
        "sell_through_rate_30d", "average_days_to_sale", "source_confidence",
    ])
    valid_metric = df[[
        c for c in [
            "sales_7d", "sales_30d", "median_sold_price_30d",
            "sell_through_rate_30d", "average_days_to_sale",
        ] if c in df.columns
    ]].notna().any(axis=1)
    df = df[df["investment_product_id"].notna() & valid_metric].copy()

    connection = get_connection()
    imported = 0
    try:
        for _, row in df.iterrows():
            connection.execute(
                """
                INSERT INTO sales_observations (
                    observation_date, investment_product_id, source_name,
                    sales_7d, sales_30d, median_sold_price_30d,
                    sell_through_rate_30d, average_days_to_sale,
                    source_confidence, raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_date, investment_product_id, source_name) DO UPDATE SET
                    sales_7d=excluded.sales_7d,
                    sales_30d=excluded.sales_30d,
                    median_sold_price_30d=excluded.median_sold_price_30d,
                    sell_through_rate_30d=excluded.sell_through_rate_30d,
                    average_days_to_sale=excluded.average_days_to_sale,
                    source_confidence=excluded.source_confidence,
                    raw_payload=excluded.raw_payload,
                    created_at=CURRENT_TIMESTAMP
                """,
                (
                    row.get("observation_date"),
                    row.get("investment_product_id"),
                    row.get("source_name") or "manual_or_external",
                    row.get("sales_7d"),
                    row.get("sales_30d"),
                    row.get("median_sold_price_30d"),
                    row.get("sell_through_rate_30d"),
                    row.get("average_days_to_sale"),
                    row.get("source_confidence"),
                    json.dumps(row.dropna().to_dict(), default=str),
                ),
            )
            imported += 1
        connection.commit()
    finally:
        connection.close()

    return {"rows_read": len(pd.read_csv(path)), "rows_imported": imported, "message": "OK"}


def import_all_market_inputs():
    return {
        "supply": import_supply_observations(),
        "sales": import_sales_observations(),
    }
