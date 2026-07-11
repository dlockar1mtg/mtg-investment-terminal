from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import math
import pandas as pd

from config import (
    PRODUCT_MAP_FILE,
    SOURCE_CACHE_DIR,
    MAX_PRICE_AGE_HOURS,
    MIN_PRICE_DATA_QUALITY,
    DATABASE_FILE,
)

def _parse_datetime(value):
    if pd.isna(value) or value == "":
        return None
    try:
        return pd.to_datetime(value, utc=True).to_pydatetime()
    except Exception:
        return None

def _hours_old(value):
    dt = _parse_datetime(value)
    if dt is None:
        return math.inf
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600

def load_product_map(path=PRODUCT_MAP_FILE):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=[
            "box_name",
            "tcgplayer_product_id",
            "tcgcsv_category_id",
            "tcgcsv_group_id",
            "source_product_name",
            "source_url",
            "verified",
            "notes",
        ])
    return pd.read_csv(path)

def load_sqlite_latest_prices():
    try:
        from database.db import latest_prices
        if Path(DATABASE_FILE).exists():
            df = latest_prices(DATABASE_FILE)
            if not df.empty:
                return df
    except Exception:
        pass
    return pd.DataFrame()

def load_local_price_cache(cache_dir=SOURCE_CACHE_DIR):
    sqlite_df = load_sqlite_latest_prices()
    if not sqlite_df.empty:
        return sqlite_df

    path = Path(cache_dir) / "latest_prices.csv"
    if not path.exists():
        return pd.DataFrame(columns=[
            "box_name",
            "tcgplayer_product_id",
            "price_source",
            "market_price",
            "low_price",
            "last_price_checked",
            "price_data_quality",
        ])
    return pd.read_csv(path)

def calculate_price_data_quality(row, max_age_hours=MAX_PRICE_AGE_HOURS):
    if "price_data_quality" in row and not pd.isna(row.get("price_data_quality")):
        try:
            existing = int(row.get("price_data_quality"))
            # Still penalize stale source data.
            age = _hours_old(row.get("last_price_checked"))
            if age > max_age_hours:
                return max(0, existing - min(35, int((age - max_age_hours) / 12) + 10))
            return existing
        except Exception:
            pass

    quality = 100
    market_price = row.get("market_price")
    if pd.isna(market_price) or float(market_price) <= 0:
        quality -= 55

    product_id = row.get("tcgplayer_product_id")
    if pd.isna(product_id) or str(product_id).strip() == "":
        quality -= 15

    source = str(row.get("price_source", "")).lower()
    if source in ["manual_seed", "sample", "unknown", ""]:
        quality -= 20
    elif source == "manual_verified":
        quality -= 8
    elif source in ["tcgcsv", "tcgplayer_api"]:
        quality -= 0
    else:
        quality -= 10

    age = _hours_old(row.get("last_price_checked"))
    if age == math.inf:
        quality -= 25
    elif age > max_age_hours:
        quality -= min(35, int((age - max_age_hours) / 12) + 10)

    low_price = row.get("low_price")
    if pd.isna(low_price) or float(low_price) <= 0:
        quality -= 5

    return int(max(0, min(100, quality)))

def refresh_price_data(input_df, allow_stale_fallback=True):
    df = input_df.copy()

    product_map = load_product_map()
    if not product_map.empty:
        map_cols = [c for c in product_map.columns if c == "box_name" or c not in df.columns]
        df = df.merge(product_map[map_cols], on="box_name", how="left")

    latest = load_local_price_cache()
    if not latest.empty:
        latest = latest[[c for c in [
            "box_name",
            "tcgplayer_product_id",
            "price_source",
            "market_price",
            "low_price",
            "last_price_checked",
            "price_data_quality",
        ] if c in latest.columns]]
        df = df.merge(latest, on="box_name", how="left", suffixes=("", "_source"))

    # Resolve source columns.
    for col in ["tcgplayer_product_id", "price_source", "market_price", "low_price", "last_price_checked", "price_data_quality"]:
        source_col = f"{col}_source"
        if source_col in df.columns:
            if col not in df.columns:
                df[col] = df[source_col]
            else:
                df[col] = df[source_col].combine_first(df[col])

    for col in ["tcgplayer_product_id", "price_source", "market_price", "low_price", "last_price_checked", "price_data_quality"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["market_price"] = pd.to_numeric(df["market_price"], errors="coerce")
    df["current_price"] = pd.to_numeric(df["current_price"], errors="coerce")

    fallback_mask = df["market_price"].isna() | (df["market_price"] <= 0)
    if allow_stale_fallback:
        df.loc[fallback_mask, "market_price"] = df.loc[fallback_mask, "current_price"]
        df.loc[fallback_mask, "price_source"] = df.loc[fallback_mask, "price_source"].fillna("manual_seed")
        df.loc[fallback_mask, "last_price_checked"] = df.loc[fallback_mask, "last_price_checked"].fillna("not_checked")

    df["current_price"] = df["market_price"]

    df["low_price"] = pd.to_numeric(df["low_price"], errors="coerce")
    if "estimated_floor_price" in df.columns:
        df.loc[df["low_price"].isna(), "low_price"] = df.loc[df["low_price"].isna(), "estimated_floor_price"]

    df["price_age_hours"] = df["last_price_checked"].apply(_hours_old)
    df["price_data_quality"] = df.apply(calculate_price_data_quality, axis=1)

    df["price_status"] = "OK"
    df.loc[df["price_age_hours"] > MAX_PRICE_AGE_HOURS, "price_status"] = "STALE"
    df.loc[df["price_data_quality"] < MIN_PRICE_DATA_QUALITY, "price_status"] = "LOW_QUALITY"
    df.loc[df["market_price"].isna(), "price_status"] = "MISSING"
    return df

def create_price_quality_report(df):
    cols = [
        "box_name",
        "tcgplayer_product_id",
        "price_source",
        "market_price",
        "low_price",
        "last_price_checked",
        "price_age_hours",
        "price_data_quality",
        "price_status",
    ]
    return df[[c for c in cols if c in df.columns]].copy()
