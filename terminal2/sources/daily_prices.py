from __future__ import annotations
import json
import uuid
from pathlib import Path
import pandas as pd
from collectors.tcgcsv_discovery import fetch_prices
from terminal2.config import DAILY_UPDATE_AUDIT_FILE
from terminal2.db.loaders import load_products_df, insert_price_observations


def number(value):
    try:
        return float(value) if pd.notna(value) else None
    except Exception:
        return None


def update_daily_prices(observation_date=None):
    day = observation_date or pd.Timestamp.now("UTC").date().isoformat()
    products = load_products_df()
    rows, audit = [], []
    for (category_id, group_id), group in products.groupby(["tcgcsv_category_id", "tcgcsv_group_id"]):
        try:
            prices = fetch_prices(int(category_id), int(group_id))
        except Exception as exc:
            audit.append({"group_id": group_id, "status": "failed", "message": str(exc)})
            continue
        price_pid = "productId" if "productId" in prices.columns else ("product_id" if "product_id" in prices.columns else None)
        if not price_pid:
            continue
        for _, product in group.iterrows():
            found = prices[prices[price_pid].astype(str) == str(product["tcgplayer_product_id"])]
            if found.empty:
                continue
            raw = found.iloc[0].to_dict()
            market = number(raw.get("marketPrice") or raw.get("market_price"))
            low = number(raw.get("lowPrice") or raw.get("low_price"))
            mid = number(raw.get("midPrice") or raw.get("mid_price"))
            high = number(raw.get("highPrice") or raw.get("high_price"))
            if not (market or mid or low):
                continue
            rows.append({
                "observation_date": day,
                "investment_product_id": product["investment_product_id"],
                "tcgplayer_product_id": product["tcgplayer_product_id"],
                "price_source": "tcgcsv_daily",
                "market_price": market or mid or low,
                "low_price": low,
                "mid_price": mid,
                "high_price": high,
                "price_data_quality": 95,
                "raw_payload": json.dumps(raw),
            })
        audit.append({"group_id": group_id, "status": "success", "products_checked": len(group)})
    count = insert_price_observations(rows, f"daily_{day}_{uuid.uuid4().hex[:8]}")
    Path(DAILY_UPDATE_AUDIT_FILE).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(audit).to_csv(DAILY_UPDATE_AUDIT_FILE, index=False)
    return count, pd.DataFrame(rows)
