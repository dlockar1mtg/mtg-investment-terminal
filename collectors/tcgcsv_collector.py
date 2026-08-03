from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import TCGCSV_BASE_URL, RAW_DATA_DIR
from collectors.common import as_float, now_utc, safe_get_json, save_raw_json

ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = ROOT / "data_vault/raw/mtg/collector_booster/tcgcsv"


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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_immutable_payload(payload, *, retrieval_id: str, category_id: str, group_id: str) -> tuple[Path, str]:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    digest = _sha256_bytes(encoded)
    destination = VAULT_ROOT / retrieval_id / "prices" / f"prices_{category_id}_{group_id}_{digest[:16]}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise RuntimeError(f"Immutable vault collision: {destination}")
    else:
        destination.write_bytes(encoded)
    return destination, digest


def _select_normal_subtype(price_df: pd.DataFrame, product_id_col: str, pid: str):
    matched = price_df[price_df[product_id_col].astype(str) == pid].copy()
    if matched.empty:
        return None, "PRODUCT_PRICE_NOT_FOUND", 0, 0

    subtype_col = "subTypeName" if "subTypeName" in matched.columns else "sub_type_name" if "sub_type_name" in matched.columns else None
    if subtype_col is None:
        return None, "SUBTYPE_FIELD_MISSING", int(len(matched)), 0

    normal = matched[matched[subtype_col].astype(str).str.strip().str.casefold() == "normal"]
    if len(normal) == 0:
        return None, "NORMAL_SUBTYPE_MISSING", int(len(matched)), 0
    if len(normal) > 1:
        return None, "NORMAL_SUBTYPE_DUPLICATE", int(len(matched)), int(len(normal))
    return normal.iloc[0].to_dict(), "NORMAL_SUBTYPE_UNIQUE", int(len(matched)), 1


def collect_tcgcsv_prices(product_map_file):
    """Pull governed TCGCSV prices for mapped Collector products.

    Controls:
    - raw working-cache response retained;
    - immutable content-addressed vault copy written before normalization;
    - exact product ID match required;
    - exactly one ``Normal`` subtype required;
    - arbitrary first-row selection forbidden;
    - unsafe products are returned as quarantined evidence rows, not silently dropped.
    """
    product_map = _load_product_map(product_map_file)
    if product_map.empty:
        return pd.DataFrame()

    mapped = product_map.dropna(subset=["tcgplayer_product_id", "tcgcsv_category_id", "tcgcsv_group_id"]).copy()
    if mapped.empty:
        return pd.DataFrame()

    collected_at = now_utc()
    retrieval_id = datetime.now(timezone.utc).strftime("tcgcsv-%Y%m%dT%H%M%SZ")
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
        vault_path, raw_sha256 = _write_immutable_payload(
            payload,
            retrieval_id=retrieval_id,
            category_id=category_id,
            group_id=group_id,
        )

        price_rows = _extract_price_rows(payload)
        price_df = pd.DataFrame(price_rows)
        if price_df.empty:
            continue

        product_id_col = "productId" if "productId" in price_df.columns else "product_id"
        if product_id_col not in price_df.columns:
            continue

        subset = mapped[
            (mapped["tcgcsv_category_id"].astype(str).astype(float).astype(int).astype(str) == category_id)
            & (mapped["tcgcsv_group_id"].astype(str).astype(float).astype(int).astype(str) == group_id)
        ]

        for _, product in subset.iterrows():
            pid = str(int(float(product["tcgplayer_product_id"])))
            row, selection_status, matched_count, normal_count = _select_normal_subtype(price_df, product_id_col, pid)

            base = {
                "retrieval_id": retrieval_id,
                "box_name": product["box_name"],
                "tcgplayer_product_id": pid,
                "source_name": "tcgcsv",
                "source_url": url,
                "source_timestamp": collected_at,
                "collected_at": collected_at,
                "raw_sha256": raw_sha256,
                "raw_vault_path": vault_path.relative_to(ROOT).as_posix(),
                "price_selection_status": selection_status,
                "matched_price_row_count": matched_count,
                "normal_subtype_row_count": normal_count,
                "admission_status": "PRICE_CANDIDATE" if row is not None else "QUARANTINED_PRICE_SUBTYPE",
            }

            if row is None:
                output_rows.append({
                    **base,
                    "market_price": None,
                    "low_price": None,
                    "mid_price": None,
                    "high_price": None,
                    "direct_low_price": None,
                    "sub_type_name": None,
                    "price_data_quality": 0,
                    "raw_payload": None,
                })
                continue

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
                **base,
                "market_price": market,
                "low_price": low,
                "mid_price": mid,
                "high_price": high,
                "direct_low_price": direct_low,
                "sub_type_name": row.get("subTypeName") or row.get("sub_type_name"),
                "price_data_quality": max(0, quality),
                "raw_payload": json.dumps(row, ensure_ascii=False, sort_keys=True),
            })

    return pd.DataFrame(output_rows)
