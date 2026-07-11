from __future__ import annotations

import gzip
import json
from pathlib import Path
import pandas as pd
import requests

from config import SCRYFALL_BULK_DATA_URL, RAW_DATA_DIR
from collectors.common import safe_get_json, now_utc

def get_default_cards_download_uri():
    payload = safe_get_json(SCRYFALL_BULK_DATA_URL, timeout=45)
    data = payload.get("data", [])
    for item in data:
        if item.get("type") == "default_cards":
            return item.get("download_uri")
    return None

def collect_scryfall_chase_summary(product_map_file, max_cards_per_set=25):
    '''
    Pulls Scryfall default_cards bulk file and summarizes top USD card prices by set.

    This is card/chase support data, not sealed box pricing.
    It can be slow the first time because the bulk file is large.
    '''
    product_map = pd.read_csv(product_map_file) if Path(product_map_file).exists() else pd.DataFrame()
    if product_map.empty or "scryfall_set_code" not in product_map.columns:
        return pd.DataFrame()

    set_codes = sorted(set(str(x).lower() for x in product_map["scryfall_set_code"].dropna().tolist()))
    if not set_codes:
        return pd.DataFrame()

    uri = get_default_cards_download_uri()
    if not uri:
        return pd.DataFrame()

    response = requests.get(uri, timeout=180)
    response.raise_for_status()

    raw_path = Path(RAW_DATA_DIR) / "scryfall" / "default_cards.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(response.content)

    cards = response.json()
    collected_at = now_utc()
    rows = []

    for set_code in set_codes:
        set_cards = []
        for card in cards:
            if str(card.get("set", "")).lower() != set_code:
                continue
            prices = card.get("prices") or {}
            usd = prices.get("usd") or prices.get("usd_foil") or prices.get("usd_etched")
            try:
                usd_val = float(usd) if usd is not None else None
            except Exception:
                usd_val = None
            if usd_val is not None:
                set_cards.append({
                    "set_code": set_code,
                    "card_name": card.get("name"),
                    "usd_price": usd_val,
                    "rarity": card.get("rarity"),
                    "collector_number": card.get("collector_number"),
                })

        if not set_cards:
            continue
        card_df = pd.DataFrame(set_cards).sort_values("usd_price", ascending=False).head(max_cards_per_set)
        rows.append({
            "scryfall_set_code": set_code,
            "top_card_value": round(card_df["usd_price"].max(), 2),
            "top_10_card_value": round(card_df["usd_price"].head(10).sum(), 2),
            "top_25_card_value": round(card_df["usd_price"].head(25).sum(), 2),
            "top_card_name": card_df.iloc[0]["card_name"],
            "card_count_priced": len(set_cards),
            "scryfall_collected_at": collected_at,
        })

    summary = pd.DataFrame(rows)
    if not summary.empty:
        summary.to_csv(Path(RAW_DATA_DIR) / "scryfall" / "chase_summary.csv", index=False)
    return summary
