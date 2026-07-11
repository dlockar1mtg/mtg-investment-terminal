from __future__ import annotations

from pathlib import Path
import pandas as pd

from config import MTGJSON_ALL_SETS_URL, RAW_DATA_DIR
from collectors.common import safe_get_json, save_raw_json, now_utc

def collect_mtgjson_set_metadata():
    '''
    Pulls MTGJSON SetList metadata for release dates and set names.
    This enriches projections; it is not the primary sealed box price source.
    '''
    collected_at = now_utc()
    try:
        payload = safe_get_json(MTGJSON_ALL_SETS_URL, timeout=60)
    except Exception as exc:
        print(f"MTGJSON metadata fetch failed: {exc}")
        return pd.DataFrame()

    raw_path = Path(RAW_DATA_DIR) / "mtgjson" / "SetList.json"
    save_raw_json(payload, raw_path)

    data = payload.get("data", []) if isinstance(payload, dict) else []
    rows = []
    for item in data:
        rows.append({
            "set_code": item.get("code"),
            "set_name": item.get("name"),
            "release_date": item.get("releaseDate"),
            "set_type_mtgjson": item.get("type"),
            "mtgjson_collected_at": collected_at,
        })
    return pd.DataFrame(rows)

def save_mtgjson_metadata(output_dir):
    df = collect_mtgjson_set_metadata()
    if not df.empty:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        df.to_csv(Path(output_dir) / "mtgjson_set_metadata.csv", index=False)
    return df
