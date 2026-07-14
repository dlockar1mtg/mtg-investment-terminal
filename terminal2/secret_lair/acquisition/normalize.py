from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
from terminal2.secret_lair.backfill.sources import CATALOG_COLUMNS, SOURCE_PRICE_COLUMNS
from terminal2.secret_lair.identifiers import normalize_text

def _mapped(frame: pd.DataFrame, mapping: dict[str,str]) -> pd.DataFrame:
    inverse={source:target for target,source in mapping.items() if source in frame.columns}
    return frame.rename(columns=inverse).copy()

def normalize_catalog(frame: pd.DataFrame, source_name: str, mapping: dict[str,str], acquired_at: str) -> pd.DataFrame:
    frame=_mapped(frame,mapping)
    for c in CATALOG_COLUMNS:
        if c not in frame.columns: frame[c]=""
    frame=frame[list(CATALOG_COLUMNS)].copy().fillna("")
    frame["source_name"]=source_name
    for c in frame.columns: frame[c]=frame[c].map(normalize_text)
    frame["finish"]=frame["finish"].str.lower(); frame["product_family"]=frame["product_family"].str.lower()
    frame["currency"]=frame["currency"].where(frame["currency"].ne(""),"USD").str.upper()
    frame["acquired_at_utc"]=acquired_at
    return frame

def normalize_prices(frame: pd.DataFrame, source_name: str, mapping: dict[str,str], acquired_at: str, default_currency: str) -> pd.DataFrame:
    frame=_mapped(frame,mapping)
    for c in SOURCE_PRICE_COLUMNS:
        if c not in frame.columns: frame[c]=""
    frame=frame[list(SOURCE_PRICE_COLUMNS)].copy().fillna("")
    frame["source_name"]=source_name
    frame["currency"]=frame["currency"].where(frame["currency"].astype(str).str.strip().ne(""),default_currency).str.upper()
    for c in ("market_price","low_price","listing_count","sales_count_30d","price_data_quality"):
        frame[c]=pd.to_numeric(frame[c],errors="coerce")
    parsed=pd.to_datetime(frame["observation_date"],errors="coerce")
    frame["observation_date"]=parsed.dt.date.astype("string").fillna("")
    frame["acquired_at_utc"]=acquired_at
    return frame
