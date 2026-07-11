from pathlib import Path
from datetime import date
import pandas as pd

def ensure_dirs(paths):
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)

def read_input_csv(path):
    return pd.read_csv(path)

def write_csv(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)

def save_price_snapshot(df, history_dir):
    today = date.today().isoformat()
    cols = [
        "investment_product_id",
        "approved_tcgplayer_product_id",
        "box_name",
        "set_name",
        "set_type",
        "current_price",
        "price_source",
        "price_data_quality",
        "investment_score",
        "risk_adjusted_score",
        "expected_cagr",
        "projection_confidence",
        "rating",
        "buy_signal",
        "target_buy_price",
        "investment_feature_score",
        "history_confidence",
        "momentum_score",
        "drawdown_score",
        "price_stability_score",
    ]
    available = [c for c in cols if c in df.columns]
    snapshot = df[available].copy()
    snapshot["snapshot_date"] = today
    out = Path(history_dir) / f"price_snapshot_{today}.csv"
    snapshot.to_csv(out, index=False)
    return out
