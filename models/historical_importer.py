from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from config import (
    PRODUCT_MASTER_FILE,
    DAILY_PRICE_OBSERVATIONS_FILE,
    HISTORICAL_IMPORT_TEMPLATE_FILE,
    HISTORICAL_IMPORT_FILE,
    HISTORICAL_IMPORT_AUDIT_FILE,
)
from models.market_database import build_rolling_price_metrics


REQUIRED_IMPORT_COLUMNS = [
    "observation_date",
    "investment_product_id",
    "tcgplayer_product_id",
    "box_name",
    "set_name",
    "current_price",
    "low_price",
    "price_source",
    "price_data_quality",
]


def load_product_master():
    path = Path(PRODUCT_MASTER_FILE)
    if not path.exists():
        raise FileNotFoundError(f"Product master not found: {path}")
    return pd.read_csv(path, dtype=str)


def create_historical_import_template():
    """
    Creates a template with one row per approved investment product.

    The user can copy rows downward for historical dates and fill current_price.
    """
    master = load_product_master()
    approved = master[master["approval_status"].astype(str).str.lower() == "approved"].copy()

    if approved.empty:
        raise RuntimeError("No approved product master rows found. Run python run.py first.")

    template = pd.DataFrame({
        "observation_date": "",
        "investment_product_id": approved["investment_product_id"],
        "tcgplayer_product_id": approved["approved_tcgplayer_product_id"],
        "box_name": approved["box_name"],
        "set_name": approved["set_name"],
        "current_price": "",
        "low_price": "",
        "price_source": "historical_manual_import",
        "price_data_quality": 80,
        "source_note": "Fill observation_date and current_price. Duplicate rows for multiple historical dates.",
    })

    path = Path(HISTORICAL_IMPORT_TEMPLATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(path, index=False)
    return template


def _validate_import(df):
    missing = [c for c in REQUIRED_IMPORT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Historical import file missing required columns: {missing}")

    clean = df.copy()
    clean["observation_date"] = pd.to_datetime(clean["observation_date"], errors="coerce").dt.date.astype(str)
    clean["current_price"] = pd.to_numeric(clean["current_price"], errors="coerce")
    clean["low_price"] = pd.to_numeric(clean["low_price"], errors="coerce")
    clean["price_data_quality"] = pd.to_numeric(clean["price_data_quality"], errors="coerce").fillna(70)

    clean = clean.dropna(subset=["investment_product_id", "observation_date", "current_price"])
    clean = clean[clean["current_price"] > 0].copy()
    clean["investment_product_id"] = clean["investment_product_id"].astype(str)
    clean["tcgplayer_product_id"] = clean["tcgplayer_product_id"].astype(str)

    return clean


def import_historical_prices(import_file=None):
    """
    Imports historical observations into daily_price_observations.csv.

    This allows the model to instantly calculate rolling metrics from external
    historical data rather than waiting months for daily runs.
    """
    if import_file is None:
        import_file = HISTORICAL_IMPORT_FILE

    import_path = Path(import_file)
    if not import_path.exists():
        create_historical_import_template()
        raise FileNotFoundError(
            f"Historical import file not found: {import_path}. "
            f"Template created at: {HISTORICAL_IMPORT_TEMPLATE_FILE}"
        )

    raw = pd.read_csv(import_path, dtype={"investment_product_id": str, "tcgplayer_product_id": str})
    clean = _validate_import(raw)

    obs_path = Path(DAILY_PRICE_OBSERVATIONS_FILE)
    obs_path.parent.mkdir(parents=True, exist_ok=True)

    if obs_path.exists():
        existing = pd.read_csv(obs_path, dtype={"investment_product_id": str, "tcgplayer_product_id": str})
        combined = pd.concat([existing, clean[REQUIRED_IMPORT_COLUMNS]], ignore_index=True, sort=False)
    else:
        combined = clean[REQUIRED_IMPORT_COLUMNS].copy()

    combined["observation_date"] = pd.to_datetime(combined["observation_date"], errors="coerce").dt.date.astype(str)
    combined["current_price"] = pd.to_numeric(combined["current_price"], errors="coerce")
    combined = combined.dropna(subset=["investment_product_id", "observation_date", "current_price"])

    combined = (
        combined.sort_values(["investment_product_id", "observation_date", "price_data_quality"])
                .drop_duplicates(subset=["investment_product_id", "observation_date"], keep="last")
                .copy()
    )

    combined.to_csv(obs_path, index=False)

    audit = pd.DataFrame([{
        "import_file": str(import_path),
        "raw_rows": len(raw),
        "valid_rows_imported": len(clean),
        "total_daily_observations_after_import": len(combined),
        "unique_products_after_import": combined["investment_product_id"].nunique(),
        "earliest_observation": combined["observation_date"].min(),
        "latest_observation": combined["observation_date"].max(),
    }])

    audit_path = Path(HISTORICAL_IMPORT_AUDIT_FILE)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_path, index=False)

    metrics = build_rolling_price_metrics()

    return {
        "audit": audit,
        "rolling_metrics": metrics,
        "daily_observations": combined,
    }


def summarize_historical_database():
    obs_path = Path(DAILY_PRICE_OBSERVATIONS_FILE)
    if not obs_path.exists():
        return pd.DataFrame()

    obs = pd.read_csv(obs_path, dtype={"investment_product_id": str, "tcgplayer_product_id": str})
    if obs.empty:
        return pd.DataFrame()

    obs["observation_date"] = pd.to_datetime(obs["observation_date"], errors="coerce")
    obs["current_price"] = pd.to_numeric(obs["current_price"], errors="coerce")
    obs = obs.dropna(subset=["investment_product_id", "observation_date", "current_price"])

    rows = []
    for pid, group in obs.groupby("investment_product_id"):
        group = group.sort_values("observation_date")
        latest = group.iloc[-1]
        rows.append({
            "investment_product_id": pid,
            "box_name": latest.get("box_name"),
            "observations": len(group),
            "earliest_date": group["observation_date"].min().date().isoformat(),
            "latest_date": group["observation_date"].max().date().isoformat(),
            "latest_price": round(float(latest["current_price"]), 2),
            "min_price": round(float(group["current_price"].min()), 2),
            "max_price": round(float(group["current_price"].max()), 2),
        })
    return pd.DataFrame(rows).sort_values(["observations", "box_name"], ascending=[False, True])
