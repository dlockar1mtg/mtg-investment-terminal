from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from config import TCGCSV_BASE_URL, RAW_DATA_DIR
from collectors.common import safe_get_json, save_raw_json, now_utc, as_float

def _load_product_map(product_map_file):
    if not Path(product_map_file).exists():
        return pd.DataFrame()
    df = pd.read_csv(product_map_file)
    for col in ["tcgcsv_category_id", "tcgcsv_group_id", "tcgplayer_product_id"]:
        if col not in df.columns:
            df[col] = None
    return df

def _extract_price_rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ["results", "data", "prices"]:
            if key in payload and isinstance(payload[key], list):
                return payload[key]
    return []

def collect_tcgcsv_prices(product_map_file):
    '''
    Pull TCGCSV group price files for mapped products.

    Required mapping columns:
    - box_name
    - tcgplayer_product_id
    - tcgcsv_category_id, usually 3 for Magic
    - tcgcsv_group_id, the TCGplayer group/set ID

    TCGCSV URL pattern:
    https://tcgcsv.com/tcgplayer/{categoryId}/{groupId}/prices
    '''
    product_map = _load_product_map(product_map_file)
    if product_map.empty:
        return pd.DataFrame()

    mapped = product_map.dropna(subset=["tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id"]).copy()
    if mapped.empty:
        return pd.DataFrame()

    collected_at = now_utc()
    output_rows = []

    group_keys = mapped[["tcgcsv_category_id", "tcgcsv_group_id"]].drop_duplicates()
    for _, group in group_keys.iterrows():
        category_id = str(int(float(group["tcgcsv_category_id"])))
        group_id = str(int(float(group["tcgcsv_group_id"])))
        url = f"{TCGCSV_BASE_URL}/{category_id}/{group_id}/prices"

        try:
            payload = safe_get_json(url)
        except Exception as exc:
            print(f"TCGCSV fetch failed for category={category_id}, group={group_id}: {exc}")
            continue

        raw_path = Path(RAW_DATA_DIR) / "tcgcsv" / f"prices_{category_id}_{group_id}.json"
        save_raw_json(payload, raw_path)

        price_rows = _extract_price_rows(payload)
        price_df = pd.DataFrame(price_rows)
        if price_df.empty:
            continue

        # Common TCGCSV fields are often camelCase.
        product_id_col = "productId" if "productId" in price_df.columns else "product_id"
        if product_id_col not in price_df.columns:
            continue

        subset = mapped[
            (mapped["tcgcsv_category_id"].astype(str).astype(float).astype(int).astype(str) == category_id) &
            (mapped["tcgcsv_group_id"].astype(str).astype(float).astype(int).astype(str) == group_id)
        ]

        for _, product in subset.iterrows():
            pid = str(int(float(product["tcgplayer_product_id"])))
            matched = price_df[price_df[product_id_col].astype(str) == pid]
            if matched.empty:
                continue

            # Prefer first row. Some products can have multiple price objects by subtype.
            row = matched.iloc[0].to_dict()
            market = as_float(row.get("marketPrice") or row.get("market_price"))
            low = as_float(row.get("lowPrice") or row.get("low_price"))
            mid = as_float(row.get("midPrice") or row.get("mid_price"))
            high = as_float(row.get("highPrice") or row.get("high_price"))
            direct_low = as_float(row.get("directLowPrice") or row.get("direct_low_price"))

            quality = 100
            if market is None:
                quality -= 50
            if low is None:
                quality -= 5

            output_rows.append({
                "box_name": product["box_name"],
                "tcgplayer_product_id": pid,
                "source_name": "tcgcsv",
                "market_price": market,
                "low_price": low,
                "mid_price": mid,
                "high_price": high,
                "direct_low_price": direct_low,
                "sub_type_name": row.get("subTypeName") or row.get("sub_type_name"),
                "source_timestamp": collected_at,
                "collected_at": collected_at,
                "price_data_quality": max(0, quality),
                "raw_payload": json.dumps(row),
            })

    return pd.DataFrame(output_rows)
