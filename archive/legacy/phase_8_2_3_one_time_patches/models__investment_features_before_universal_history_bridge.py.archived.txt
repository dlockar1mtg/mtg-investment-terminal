from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import numpy as np

from config import (
    HISTORY_DIR,
    INVESTMENT_FEATURES_FILE,
    HISTORICAL_METRICS_FILE,
    RELEASE_METADATA_FILE,
)


def load_history_snapshots(history_dir=HISTORY_DIR):
    """
    Loads both old daily snapshots and v10-compatible snapshots.

    Expected useful fields:
    - snapshot_date
    - box_name
    - current_price / market_price
    - price_source
    """
    history_dir = Path(history_dir)
    if not history_dir.exists():
        return pd.DataFrame()

    frames = []
    for file in history_dir.glob("*.csv"):
        try:
            df = pd.read_csv(file)
            if "snapshot_date" not in df.columns:
                # infer from filename when possible
                stem = file.stem
                inferred = stem.replace("price_snapshot_", "")
                df["snapshot_date"] = inferred
            frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    hist = pd.concat(frames, ignore_index=True, sort=False)

    if "current_price" not in hist.columns and "market_price" in hist.columns:
        hist["current_price"] = hist["market_price"]

    hist["current_price"] = pd.to_numeric(hist.get("current_price"), errors="coerce")
    hist["snapshot_date"] = pd.to_datetime(hist["snapshot_date"], errors="coerce")
    hist = hist.dropna(subset=["box_name", "snapshot_date", "current_price"])
    hist = hist[hist["current_price"] > 0].copy()
    hist = hist.sort_values(["box_name", "snapshot_date"])
    return hist


def _price_days_ago(group, days):
    if group.empty:
        return np.nan
    latest_date = group["snapshot_date"].max()
    target_date = latest_date - pd.Timedelta(days=days)
    eligible = group[group["snapshot_date"] <= target_date]
    if eligible.empty:
        return np.nan
    return float(eligible.iloc[-1]["current_price"])


def _safe_return(current, previous):
    if pd.isna(previous) or previous <= 0 or pd.isna(current):
        return np.nan
    return (current / previous) - 1


def build_historical_metrics(history_df):
    if history_df is None or history_df.empty:
        return pd.DataFrame()

    rows = []
    for box_name, group in history_df.groupby("box_name"):
        group = group.sort_values("snapshot_date").copy()
        latest = group.iloc[-1]
        current = float(latest["current_price"])

        prices = group["current_price"].astype(float)
        high = float(prices.max())
        low = float(prices.min())

        returns = prices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        volatility = float(returns.std() * math.sqrt(365)) if len(returns) >= 2 else np.nan

        p30 = _price_days_ago(group, 30)
        p90 = _price_days_ago(group, 90)
        p180 = _price_days_ago(group, 180)
        p365 = _price_days_ago(group, 365)

        rows.append({
            "box_name": box_name,
            "history_observations": len(group),
            "first_snapshot_date": group["snapshot_date"].min().date().isoformat(),
            "latest_snapshot_date": group["snapshot_date"].max().date().isoformat(),
            "current_price_history": round(current, 2),
            "history_high_price": round(high, 2),
            "history_low_price": round(low, 2),
            "drawdown_from_high": round((current / high) - 1, 4) if high > 0 else np.nan,
            "distance_from_low": round((current / low) - 1, 4) if low > 0 else np.nan,
            "return_30d": round(_safe_return(current, p30), 4) if not pd.isna(p30) else np.nan,
            "return_90d": round(_safe_return(current, p90), 4) if not pd.isna(p90) else np.nan,
            "return_180d": round(_safe_return(current, p180), 4) if not pd.isna(p180) else np.nan,
            "return_365d": round(_safe_return(current, p365), 4) if not pd.isna(p365) else np.nan,
            "annualized_volatility": round(volatility, 4) if not pd.isna(volatility) else np.nan,
        })

    metrics = pd.DataFrame(rows)
    Path(HISTORICAL_METRICS_FILE).parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(HISTORICAL_METRICS_FILE, index=False)
    return metrics


def load_release_metadata():
    path = Path(RELEASE_METADATA_FILE)
    if not path.exists():
        return pd.DataFrame(columns=[
            "box_name",
            "release_date",
            "release_msrp",
            "notes",
        ])
    df = pd.read_csv(path)
    return df


def _score_momentum(row):
    # Conservative momentum score. Positive 90/180d helps, sharp recent spikes hurt.
    r90 = row.get("return_90d")
    r180 = row.get("return_180d")

    score = 50
    for r, weight in [(r90, 60), (r180, 40)]:
        if pd.isna(r):
            continue
        score += max(-20, min(20, r * weight))

    # Penalize extreme short-term spikes.
    r30 = row.get("return_30d")
    if not pd.isna(r30) and r30 > 0.35:
        score -= 10

    return round(max(0, min(100, score)), 2)


def _score_drawdown(row):
    dd = row.get("drawdown_from_high")
    if pd.isna(dd):
        return 50
    # Mild drawdown can be good entry; severe drawdown suggests weakness.
    if dd >= -0.05:
        return 55
    if dd >= -0.20:
        return 70
    if dd >= -0.40:
        return 55
    return 35


def _score_volatility(row):
    vol = row.get("annualized_volatility")
    if pd.isna(vol):
        return 50
    if vol < 0.15:
        return 75
    if vol < 0.30:
        return 65
    if vol < 0.55:
        return 50
    return 35


def build_investment_features(model_df):
    """
    Adds history-based feature columns to the active product-master model input.
    If there is not much history yet, v10 starts collecting it and falls back safely.
    """
    model = model_df.copy()
    hist = load_history_snapshots()
    metrics = build_historical_metrics(hist)

    if not metrics.empty:
        model = model.merge(metrics, on="box_name", how="left")
    else:
        # provide empty columns
        for col in [
            "history_observations", "history_high_price", "history_low_price",
            "drawdown_from_high", "distance_from_low", "return_30d", "return_90d",
            "return_180d", "return_365d", "annualized_volatility"
        ]:
            model[col] = np.nan

    release = load_release_metadata()
    if not release.empty:
        model = model.merge(release, on="box_name", how="left")

    # Feature scores
    model["momentum_score"] = model.apply(_score_momentum, axis=1)
    model["drawdown_score"] = model.apply(_score_drawdown, axis=1)
    model["price_stability_score"] = model.apply(_score_volatility, axis=1)

    # History confidence starts low until enough observations exist.
    obs = pd.to_numeric(model.get("history_observations"), errors="coerce").fillna(0)
    model["history_confidence"] = (obs / 30 * 100).clip(lower=0, upper=100).round(1)

    # Investment feature blend, intentionally modest until real history accumulates.
    model["investment_feature_score"] = (
        model["momentum_score"] * 0.35 +
        model["drawdown_score"] * 0.30 +
        model["price_stability_score"] * 0.20 +
        model["history_confidence"] * 0.15
    ).round(2)

    Path(INVESTMENT_FEATURES_FILE).parent.mkdir(parents=True, exist_ok=True)
    model.to_csv(INVESTMENT_FEATURES_FILE, index=False)
    return model
