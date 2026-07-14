from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from terminal2.config import ROOT_DIR
from terminal2.secret_lair.identifiers import normalize_text

SOURCE_CONFIG_PATH = Path(ROOT_DIR)/"data"/"terminal2"/"secret_lair_acquisition_sources.csv"
SOURCE_CONFIG_COLUMNS = (
 "source_name","connector_type","location","enabled","priority","source_quality",
 "default_currency","catalog_mapping_json","price_mapping_json","notes",
)

def load_source_config(path: Path = SOURCE_CONFIG_PATH) -> tuple[pd.DataFrame,bool]:
    path=Path(path)
    if not path.exists(): return pd.DataFrame(columns=SOURCE_CONFIG_COLUMNS),False
    frame=pd.read_csv(path,dtype=str).fillna("")
    for c in SOURCE_CONFIG_COLUMNS:
        if c not in frame.columns: frame[c]=""
    frame=frame[list(SOURCE_CONFIG_COLUMNS)].copy()
    for c in frame.columns: frame[c]=frame[c].map(normalize_text)
    frame["source_name"]=frame["source_name"].str.lower()
    frame["connector_type"]=frame["connector_type"].str.lower()
    frame["enabled"]=frame["enabled"].str.lower().isin({"1","true","yes","y"})
    frame["priority"]=pd.to_numeric(frame["priority"],errors="coerce").fillna(100).astype(int)
    frame["source_quality"]=pd.to_numeric(frame["source_quality"],errors="coerce").fillna(50.0)
    frame["default_currency"]=frame["default_currency"].where(frame["default_currency"].ne(""),"USD").str.upper()
    return frame,True

def parse_mapping(value: object) -> dict[str,str]:
    text=normalize_text(value)
    if not text: return {}
    parsed=json.loads(text)
    if not isinstance(parsed,dict): raise ValueError("Mapping JSON must be an object.")
    return {str(k):str(v) for k,v in parsed.items()}
