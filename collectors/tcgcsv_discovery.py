from __future__ import annotations

from pathlib import Path
import json
import re
import time
import pandas as pd

from config import (
    TCGCSV_BASE_URL,
    TCGCSV_MAGIC_CATEGORY_ID,
    AUTO_DETECT_TCGCSV_MAGIC_CATEGORY,
    TCGCSV_CATEGORY_NAME_MATCHES,
    TCGCSV_REQUEST_DELAY_SECONDS,
    TCGCSV_MAX_GROUPS,
    RAW_DATA_DIR,
    COLLECTOR_BOX_INCLUDE_TERMS,
    COLLECTOR_BOX_EXCLUDE_TERMS,
)
from collectors.common import safe_get_json, save_raw_json, now_utc, as_float

def _results(payload):
    if isinstance(payload, dict):
        val = payload.get("results") or payload.get("data") or []
        return val if isinstance(val, list) else []
    return payload if isinstance(payload, list) else []

def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

def fetch_categories():
    url = f"{TCGCSV_BASE_URL}/categories"
    payload = safe_get_json(url, timeout=90, source_name="tcgcsv_categories")
    save_raw_json(payload, Path(RAW_DATA_DIR) / "tcgcsv" / "categories.json")
    return pd.DataFrame(_results(payload))

def detect_magic_category_id():
    categories = fetch_categories()
    if categories.empty:
        raise RuntimeError("TCGCSV categories endpoint returned no categories.")

    categories.to_csv(Path(RAW_DATA_DIR) / "tcgcsv" / "categories.csv", index=False)

    match_terms = [normalize_name(x) for x in TCGCSV_CATEGORY_NAME_MATCHES]

    for _, row in categories.iterrows():
        fields = [
            row.get("name", ""),
            row.get("displayName", ""),
            row.get("seoCategoryName", ""),
        ]
        combined = normalize_name(" ".join(str(x) for x in fields))
        if any(term in combined for term in match_terms):
            cid = row.get("categoryId") or row.get("category_id")
            if pd.notna(cid):
                print(f"Auto-detected TCGCSV Magic category: {cid} ({combined})")
                return int(cid)

    raise RuntimeError(
        "Could not auto-detect Magic category. Run python discover_categories.py and check data/raw/tcgcsv/categories.csv"
    )

def resolve_category_id(category_id=None):
    if category_id is not None:
        return int(category_id)

    if TCGCSV_MAGIC_CATEGORY_ID not in [None, "", "None"]:
        return int(TCGCSV_MAGIC_CATEGORY_ID)

    if AUTO_DETECT_TCGCSV_MAGIC_CATEGORY:
        return detect_magic_category_id()

    raise RuntimeError("No TCGCSV Magic category configured and auto-detection is disabled.")

def is_collector_booster_box(product_name):
    n = normalize_name(product_name)
    include = any(term in n for term in COLLECTOR_BOX_INCLUDE_TERMS)
    exclude = any(term in n for term in COLLECTOR_BOX_EXCLUDE_TERMS)
    return include and not exclude

def infer_set_type(group_name, product_name):
    text = normalize_name(f"{group_name} {product_name}")
    if any(x in text for x in ["universes beyond", "lord of the rings", "final fantasy", "fallout", "doctor who", "warhammer", "assassin s creed", "marvel"]):
        return "Universes Beyond"
    if "masters" in text or "double masters" in text or "commander masters" in text:
        return "Masters"
    if "modern horizons" in text:
        return "Modern Horizons"
    if "commander" in text:
        return "Commander"
    return "Standard"

def default_model_factors(group_name, product_name, published_on=None):
    text = normalize_name(f"{group_name} {product_name}")
    set_type = infer_set_type(group_name, product_name)

    supply, demand, chase, ip, historical, liquidity = 62, 68, 65, 60, 62, 70
    reprint, dump, liq_risk, concentration, uncertainty = 50, 55, 35, 50, 45

    if set_type == "Universes Beyond":
        demand += 12; ip += 25; liquidity += 5; uncertainty += 5
    if set_type == "Masters":
        demand += 10; chase += 12; historical += 12; supply += 5
    if set_type == "Modern Horizons":
        demand += 14; chase += 10; historical += 10; liquidity += 8

    if "lord of the rings" in text:
        demand, chase, ip, historical, liquidity = 98, 96, 100, 92, 95
        supply, reprint, dump, concentration = 88, 35, 30, 70
    if "final fantasy" in text:
        demand, chase, ip, liquidity = 93, 89, 100, 82
        supply, reprint, dump, concentration, uncertainty = 72, 42, 62, 58, 72
    if "double masters 2022" in text:
        demand, chase, historical, liquidity = 92, 91, 91, 86
        supply, reprint, dump, concentration = 84, 35, 30, 52
    if "kamigawa neon dynasty" in text:
        demand, chase, ip, historical, liquidity = 91, 88, 76, 90, 88
        supply, reprint, dump, concentration = 86, 32, 28, 44

    return {
        "set_type": set_type,
        "supply_score": min(supply, 100),
        "demand_score": min(demand, 100),
        "chase_score": min(chase, 100),
        "ip_score": min(ip, 100),
        "historical_score": min(historical, 100),
        "liquidity_score": min(liquidity, 100),
        "reprint_risk": max(0, min(reprint, 100)),
        "supply_dump_risk": max(0, min(dump, 100)),
        "liquidity_risk": max(0, min(liq_risk, 100)),
        "chase_concentration_risk": max(0, min(concentration, 100)),
        "new_set_uncertainty": max(0, min(uncertainty, 100)),
        "data_quality_score": 65,
        "volatility_score": 45,
    }

def estimate_months_since_release(published_on):
    if not published_on:
        return 24
    try:
        published = pd.to_datetime(published_on, utc=True)
        now = pd.Timestamp.utcnow()
        return max(0, int((now - published).days / 30.44))
    except Exception:
        return 24

def fetch_groups(category_id):
    url = f"{TCGCSV_BASE_URL}/{category_id}/groups"
    payload = safe_get_json(url, timeout=90, source_name="tcgcsv_groups")
    save_raw_json(payload, Path(RAW_DATA_DIR) / "tcgcsv" / f"groups_category_{category_id}.json")
    return pd.DataFrame(_results(payload))

def fetch_products(category_id, group_id):
    url = f"{TCGCSV_BASE_URL}/{category_id}/{group_id}/products"
    payload = safe_get_json(url, timeout=90, source_name="tcgcsv_products")
    save_raw_json(payload, Path(RAW_DATA_DIR) / "tcgcsv" / f"products_{category_id}_{group_id}.json")
    return pd.DataFrame(_results(payload))

def fetch_prices(category_id, group_id):
    url = f"{TCGCSV_BASE_URL}/{category_id}/{group_id}/prices"
    payload = safe_get_json(url, timeout=90, source_name="tcgcsv_prices")
    save_raw_json(payload, Path(RAW_DATA_DIR) / "tcgcsv" / f"prices_{category_id}_{group_id}.json")
    return pd.DataFrame(_results(payload))

def discover_collector_booster_boxes(category_id=None, sleep_seconds=None, max_groups=None):
    category_id = resolve_category_id(category_id)
    if sleep_seconds is None:
        sleep_seconds = TCGCSV_REQUEST_DELAY_SECONDS
    if max_groups is None:
        max_groups = TCGCSV_MAX_GROUPS

    print(f"Using TCGCSV category: {category_id}")

    collected_at = now_utc()
    groups = fetch_groups(category_id)
    if groups.empty:
        return pd.DataFrame(), pd.DataFrame()

    groups.to_csv(Path(RAW_DATA_DIR) / "tcgcsv" / f"groups_category_{category_id}.csv", index=False)

    if max_groups:
        groups = groups.head(int(max_groups))

    discovered = []
    price_cache_rows = []

    for group_num, group in groups.iterrows():
        group_id = group.get("groupId") or group.get("group_id")
        if pd.isna(group_id):
            continue
        try:
            group_id_int = int(group_id)
        except Exception:
            continue

        group_name = group.get("name", "")
        published_on = group.get("publishedOn") or group.get("published_on")

        try:
            products = fetch_products(category_id, group_id_int)
        except Exception as exc:
            print(f"Product fetch failed for group {group_id_int} {group_name}: {exc}")
            continue

        if products.empty or "name" not in products.columns:
            continue

        matches = products[products["name"].apply(is_collector_booster_box)].copy()
        if matches.empty:
            time.sleep(sleep_seconds)
            continue

        try:
            prices = fetch_prices(category_id, group_id_int)
        except Exception as exc:
            print(f"Price fetch failed for group {group_id_int} {group_name}: {exc}")
            prices = pd.DataFrame()

        product_id_col = "productId" if "productId" in matches.columns else "product_id"
        price_pid_col = "productId" if "productId" in prices.columns else ("product_id" if "product_id" in prices.columns else None)

        for _, product in matches.iterrows():
            product_id = product.get(product_id_col)
            product_name = product.get("name")
            official_box_name = f"{group_name} Collector Booster Box"
            model_factors = default_model_factors(group_name, product_name, published_on)

            market = low = mid = high = direct_low = None
            subtype = None
            raw_price = {}

            if price_pid_col and not prices.empty:
                matched_prices = prices[prices[price_pid_col].astype(str) == str(product_id)]
                if not matched_prices.empty:
                    pr = matched_prices.iloc[0].to_dict()
                    raw_price = pr
                    market = as_float(pr.get("marketPrice") or pr.get("market_price"))
                    low = as_float(pr.get("lowPrice") or pr.get("low_price"))
                    mid = as_float(pr.get("midPrice") or pr.get("mid_price"))
                    high = as_float(pr.get("highPrice") or pr.get("high_price"))
                    direct_low = as_float(pr.get("directLowPrice") or pr.get("direct_low_price"))
                    subtype = pr.get("subTypeName") or pr.get("sub_type_name")

            current_price = market or mid or low or 0
            estimated_floor = low or (current_price * 0.82 if current_price else 0)
            estimated_ceiling = high or (current_price * 1.35 if current_price else 0)
            fair_value = market or mid or current_price

            record = {
                "box_name": official_box_name,
                "set_name": group_name,
                "official_product_name": product_name,
                "set_type": model_factors.pop("set_type"),
                "months_since_release": estimate_months_since_release(published_on),
                "current_price": round(float(current_price), 2) if current_price else 0,
                "estimated_floor_price": round(float(estimated_floor), 2) if estimated_floor else 0,
                "estimated_ceiling_price": round(float(estimated_ceiling), 2) if estimated_ceiling else 0,
                "fair_value_estimate": round(float(fair_value), 2) if fair_value else 0,
                "tcgplayer_product_id": product_id,
                "tcgcsv_category_id": category_id,
                "tcgcsv_group_id": group_id_int,
                "price_source": "tcgcsv" if market else "tcgcsv_no_market",
                "market_price": market,
                "low_price": low,
                "mid_price": mid,
                "high_price": high,
                "last_price_checked": collected_at,
                "source_product_name": product_name,
                "source_group_name": group_name,
                "published_on": published_on,
                **model_factors,
            }
            discovered.append(record)

            if market:
                price_cache_rows.append({
                    "box_name": official_box_name,
                    "tcgplayer_product_id": product_id,
                    "source_name": "tcgcsv",
                    "market_price": market,
                    "low_price": low,
                    "mid_price": mid,
                    "high_price": high,
                    "direct_low_price": direct_low,
                    "sub_type_name": subtype,
                    "source_timestamp": collected_at,
                    "collected_at": collected_at,
                    "price_data_quality": 100,
                    "raw_payload": json.dumps(raw_price),
                })

        print(f"Discovered {len(matches)} collector booster product(s) in group {group_id_int}: {group_name}")
        time.sleep(sleep_seconds)

    discovered_df = pd.DataFrame(discovered)
    price_df = pd.DataFrame(price_cache_rows)
    return discovered_df, price_df
