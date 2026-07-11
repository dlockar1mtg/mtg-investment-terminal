from __future__ import annotations

import json
import pandas as pd
import requests

from config import TCGPLAYER_ACCESS_TOKEN
from collectors.common import now_utc, as_float

def collect_tcgplayer_api_prices(product_map_file):
    '''
    Optional connector.

    This only works if you already have TCGplayer API access and set:
    TCGPLAYER_ACCESS_TOKEN

    TCGplayer documentation says new API access is no longer being granted,
    so this collector is disabled unless credentials exist.
    '''
    if not TCGPLAYER_ACCESS_TOKEN:
        return pd.DataFrame()

    product_map = pd.read_csv(product_map_file)
    product_map = product_map.dropna(subset=["tcgplayer_product_id"]).copy()
    if product_map.empty:
        return pd.DataFrame()

    ids = [str(int(float(x))) for x in product_map["tcgplayer_product_id"].tolist()]
    id_string = ",".join(ids)
    url = f"https://api.tcgplayer.com/pricing/product/{id_string}"

    headers = {
        "Accept": "application/json",
        "Authorization": f"bearer {TCGPLAYER_ACCESS_TOKEN}",
    }

    response = requests.get(url, headers=headers, timeout=45)
    response.raise_for_status()
    payload = response.json()

    results = payload.get("results", []) if isinstance(payload, dict) else []
    prices = pd.DataFrame(results)
    if prices.empty:
        return pd.DataFrame()

    collected_at = now_utc()
    output = []
    for _, mapping in product_map.iterrows():
        pid = str(int(float(mapping["tcgplayer_product_id"])))
        product_prices = prices[prices["productId"].astype(str) == pid]
        if product_prices.empty:
            continue
        row = product_prices.iloc[0].to_dict()
        market = as_float(row.get("marketPrice"))
        low = as_float(row.get("lowPrice"))
        output.append({
            "box_name": mapping["box_name"],
            "tcgplayer_product_id": pid,
            "source_name": "tcgplayer_api",
            "market_price": market,
            "low_price": low,
            "mid_price": as_float(row.get("midPrice")),
            "high_price": as_float(row.get("highPrice")),
            "direct_low_price": as_float(row.get("directLowPrice")),
            "sub_type_name": row.get("subTypeName"),
            "source_timestamp": collected_at,
            "collected_at": collected_at,
            "price_data_quality": 100 if market is not None else 50,
            "raw_payload": json.dumps(row),
        })
    return pd.DataFrame(output)
