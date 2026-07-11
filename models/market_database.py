from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from config import (
    DAILY_PRICE_OBSERVATIONS_FILE,
    ROLLING_PRICE_METRICS_FILE,
)


def _today_utc_date():
    return pd.Timestamp.utcnow().date().isoformat()


def _series_from(df, col_name, default=None):
    """
    Always returns a Series aligned to df.index.
    Prevents scalar/default `.fillna()` errors.
    """
    if col_name in df.columns:
        return df[col_name]
    return pd.Series(default, index=df.index)


def append_daily_price_observations(model_df):
    if model_df is None or model_df.empty:
        return pd.DataFrame()

    model = model_df.copy()

    obs = pd.DataFrame(index=model.index)
    obs["observation_date"] = _today_utc_date()
    obs["investment_product_id"] = _series_from(model, "investment_product_id").astype(str)
    obs["tcgplayer_product_id"] = _series_from(
        model,
        "approved_tcgplayer_product_id",
        None
    ).fillna(_series_from(model, "tcgplayer_product_id", None)).astype(str)
    obs["box_name"] = _series_from(model, "box_name")
    obs["set_name"] = _series_from(model, "set_name")
    obs["current_price"] = pd.to_numeric(_series_from(model, "current_price"), errors="coerce")
    obs["low_price"] = pd.to_numeric(
        _series_from(model, "low_price", None).fillna(_series_from(model, "estimated_floor_price", None)),
        errors="coerce",
    )
    obs["price_source"] = _series_from(model, "price_source", "unknown")
    obs["price_data_quality"] = pd.to_numeric(
        _series_from(model, "price_data_quality", 95),
        errors="coerce",
    ).fillna(95)

    obs = obs.dropna(subset=["investment_product_id", "current_price"])
    obs = obs[obs["current_price"] > 0].copy()

    path = Path(DAILY_PRICE_OBSERVATIONS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = pd.read_csv(path, dtype={"investment_product_id": str, "tcgplayer_product_id": str})
        combined = pd.concat([existing, obs], ignore_index=True, sort=False)
    else:
        combined = obs

    combined["observation_date"] = pd.to_datetime(combined["observation_date"], errors="coerce").dt.date.astype(str)
    combined = (
        combined.sort_values(["investment_product_id", "observation_date"])
                .drop_duplicates(subset=["investment_product_id", "observation_date"], keep="last")
                .copy()
    )
    combined.to_csv(path, index=False)
    return combined


def load_daily_price_observations():
    path = Path(DAILY_PRICE_OBSERVATIONS_FILE)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"investment_product_id": str, "tcgplayer_product_id": str})
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["current_price"] = pd.to_numeric(df["current_price"], errors="coerce")
    df = df.dropna(subset=["investment_product_id", "observation_date", "current_price"])
    return df.sort_values(["investment_product_id", "observation_date"])


def _price_at_or_before(group, target_date):
    eligible = group[group["observation_date"] <= target_date]
    if eligible.empty:
        return np.nan
    return float(eligible.iloc[-1]["current_price"])


def build_rolling_price_metrics():
    df = load_daily_price_observations()
    if df.empty:
        Path(ROLLING_PRICE_METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(ROLLING_PRICE_METRICS_FILE, index=False)
        return pd.DataFrame()

    rows = []
    for product_id, g in df.groupby("investment_product_id"):
        g = g.sort_values("observation_date").copy()
        latest = g.iloc[-1]
        current = float(latest["current_price"])
        latest_date = latest["observation_date"]

        prices = g["current_price"].astype(float)
        high = float(prices.max())
        low = float(prices.min())

        row = {
            "investment_product_id": str(product_id),
            "box_name": latest.get("box_name"),
            "latest_observation_date": latest_date.date().isoformat(),
            "observations": len(g),
            "current_price_db": round(current, 2),
            "ath_price": round(high, 2),
            "atl_price": round(low, 2),
            "drawdown_from_ath": round(current / high - 1, 4) if high else np.nan,
            "distance_from_atl": round(current / low - 1, 4) if low else np.nan,
        }

        for window in [7, 14, 30, 60, 90, 180, 365]:
            cutoff = latest_date - pd.Timedelta(days=window)
            recent = g[g["observation_date"] >= cutoff]
            row[f"ma_{window}d"] = round(float(recent["current_price"].mean()), 2) if not recent.empty else np.nan
            old_price = _price_at_or_before(g, cutoff)
            row[f"return_{window}d_db"] = round(current / old_price - 1, 4) if old_price and not np.isnan(old_price) else np.nan

        returns = prices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        row["daily_return_volatility"] = round(float(returns.std()), 5) if len(returns) >= 2 else np.nan
        row["annualized_volatility_db"] = round(float(returns.std() * np.sqrt(365)), 4) if len(returns) >= 2 else np.nan
        rows.append(row)

    out = pd.DataFrame(rows)
    Path(ROLLING_PRICE_METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(ROLLING_PRICE_METRICS_FILE, index=False)
    return out


def apply_rolling_metrics(model_df):
    if model_df is None or model_df.empty:
        return model_df

    append_daily_price_observations(model_df)
    metrics = build_rolling_price_metrics()

    model = model_df.copy()
    if metrics.empty:
        return model

    model["investment_product_id"] = model["investment_product_id"].astype(str)
    metrics["investment_product_id"] = metrics["investment_product_id"].astype(str)
    model = model.merge(metrics, on="investment_product_id", how="left", suffixes=("", "_db"))
    return model
