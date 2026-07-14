import json
from pathlib import Path
import pandas as pd
from terminal2.config import ROOT_DIR
from terminal2.secret_lair.identifiers import normalize_text
DISCOVERY_CONFIG_PATH=Path(ROOT_DIR)/'data'/'terminal2'/'secret_lair_discovery_sources.csv'
DISCOVERY_STATE_PATH=Path(ROOT_DIR)/'data'/'terminal2'/'secret_lair_discovery_state.csv'
DISCOVERY_CACHE_ROOT=Path(ROOT_DIR)/'data'/'terminal2'/'secret_lair_discovery_cache'
DISCOVERY_RAW_ROOT=Path(ROOT_DIR)/'data'/'terminal2'/'secret_lair_discovery_raw'
DISCOVERY_STAGE_PATH=Path(ROOT_DIR)/'data'/'terminal2'/'secret_lair_discovery_stage_catalog.csv'
COLUMNS=('source_name','connector_type','endpoint','enabled','priority','parser_name','timeout_seconds','max_retries','cache_ttl_hours','source_quality','query_json','notes')
def load_discovery_config(path=DISCOVERY_CONFIG_PATH):
    path=Path(path)
    if not path.exists(): return pd.DataFrame(columns=COLUMNS),False
    f=pd.read_csv(path,dtype=str).fillna('')
    for c in COLUMNS:
        if c not in f.columns:f[c]=''
    f=f[list(COLUMNS)]
    for c in f.columns:f[c]=f[c].fillna('').map(normalize_text)
    f['source_name']=f['source_name'].str.lower(); f['connector_type']=f['connector_type'].str.lower(); f['parser_name']=f['parser_name'].str.lower(); f['enabled']=f['enabled'].str.lower().isin({'1','true','yes','y'})
    f['priority']=pd.to_numeric(f['priority'],errors='coerce').fillna(100).astype(int); f['timeout_seconds']=pd.to_numeric(f['timeout_seconds'],errors='coerce').fillna(30).astype(int); f['max_retries']=pd.to_numeric(f['max_retries'],errors='coerce').fillna(3).astype(int); f['cache_ttl_hours']=pd.to_numeric(f['cache_ttl_hours'],errors='coerce').fillna(24.0); f['source_quality']=pd.to_numeric(f['source_quality'],errors='coerce').fillna(50.0)
    return f,True
def parse_query(v):
    s=normalize_text(v)
    if not s:return {}
    obj=json.loads(s)
    if not isinstance(obj,dict):raise ValueError('query_json must contain an object.')
    return obj
