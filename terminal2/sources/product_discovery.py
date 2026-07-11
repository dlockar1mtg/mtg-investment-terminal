from __future__ import annotations
import re
import time
from pathlib import Path
import pandas as pd
from collectors.tcgcsv_discovery import resolve_category_id, fetch_groups, fetch_products, fetch_prices
from terminal2.config import DISCOVERY_CANDIDATES_FILE, DISCOVERY_AUDIT_FILE


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def classify_product(group_name, product_name):
    text = norm(f"{group_name} {product_name}")
    exclusions = ["play booster", "set booster", "display case", "booster case", "sample pack", "booster pack", "commander deck", "starter kit", "prerelease"]
    if any(term in text for term in exclusions):
        return None
    if "secret lair" in text:
        return "Secret Lair Drop"
    if "collector booster" in text and any(term in text for term in ["display", "box"]):
        return "Collector Booster Display"
    if "draft booster" in text and any(term in text for term in ["display", "box"]):
        return "Masters Booster Display" if "masters" in text else "Draft Booster Display"
    if "booster box" in text or "booster display" in text:
        if "collector" in text:
            return None
        return "Masters Booster Display" if "masters" in text else "Traditional Booster Display"
    return None


def candidate_score(product_name, product_type, market_price):
    text = norm(product_name)
    score = {"Collector Booster Display": 180, "Draft Booster Display": 170, "Traditional Booster Display": 170, "Masters Booster Display": 180, "Secret Lair Drop": 145}.get(product_type, 100)
    if "display" in text or "booster box" in text:
        score += 25
    if market_price and market_price > 0:
        score += 20
    if any(term in text for term in ["case", "pack", "sample"]):
        score -= 250
    return score


def _number(row, camel, snake):
    value = row.get(camel) if camel in row else row.get(snake)
    try:
        return float(value) if pd.notna(value) else None
    except Exception:
        return None


def discover_supported_products(category_id=None, sleep_seconds=0.05, max_groups=None):
    category_id = resolve_category_id(category_id)
    groups = fetch_groups(category_id)
    if max_groups:
        groups = groups.head(int(max_groups))
    rows, audit = [], []
    for _, group in groups.iterrows():
        group_id = group.get("groupId") or group.get("group_id")
        group_name = group.get("name", "")
        if pd.isna(group_id):
            continue
        try:
            products = fetch_products(category_id, int(group_id))
        except Exception as exc:
            audit.append({"group_id": group_id, "group_name": group_name, "status": "failed", "message": str(exc)})
            continue
        matches = []
        for _, product in products.iterrows():
            product_type = classify_product(group_name, product.get("name", ""))
            if product_type:
                matches.append((product, product_type))
        if not matches:
            continue
        try:
            prices = fetch_prices(category_id, int(group_id))
        except Exception:
            prices = pd.DataFrame()
        price_pid = "productId" if "productId" in prices.columns else ("product_id" if "product_id" in prices.columns else None)
        for product, product_type in matches:
            product_id = product.get("productId") or product.get("product_id")
            market = low = mid = high = None
            if price_pid and not prices.empty:
                found = prices[prices[price_pid].astype(str) == str(product_id)]
                if not found.empty:
                    price = found.iloc[0]
                    market = _number(price, "marketPrice", "market_price")
                    low = _number(price, "lowPrice", "low_price")
                    mid = _number(price, "midPrice", "mid_price")
                    high = _number(price, "highPrice", "high_price")
            product_name = product.get("name", "")
            rows.append({
                "investment_product_id": f"TCGCSV-{int(group_id)}-{product_id}",
                "set_name": group_name,
                "box_name": product_name,
                "approved_tcgplayer_product_id": str(product_id),
                "approved_product_name": product_name,
                "tcgcsv_category_id": str(category_id),
                "tcgcsv_group_id": str(int(group_id)),
                "investment_product_type": product_type,
                "approval_status": "candidate",
                "approval_method": "module1_discovery",
                "market_price": market,
                "low_price": low,
                "mid_price": mid,
                "high_price": high,
                "candidate_score": candidate_score(product_name, product_type, market),
            })
        audit.append({"group_id": group_id, "group_name": group_name, "status": "success", "candidates": len(matches)})
        time.sleep(sleep_seconds)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(["investment_product_type", "set_name", "candidate_score"], ascending=[True, True, False])
    Path(DISCOVERY_CANDIDATES_FILE).parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(DISCOVERY_CANDIDATES_FILE, index=False)
    pd.DataFrame(audit).to_csv(DISCOVERY_AUDIT_FILE, index=False)
    return candidates
