from __future__ import annotations

import numpy as np
import pandas as pd

from terminal2.db.schema import get_connection, init_db
from terminal2.db.loaders import load_price_observations_df


def _price_at_or_before(g, target_date):
    eligible = g[g["observation_date"] <= target_date]
    if eligible.empty:
        return np.nan
    return float(eligible.iloc[-1]["market_price"])


def compute_price_features():
    init_db()
    obs = load_price_observations_df()
    if obs.empty:
        return pd.DataFrame()

    obs["observation_date"] = pd.to_datetime(obs["observation_date"], errors="coerce")
    obs["market_price"] = pd.to_numeric(obs["market_price"], errors="coerce")
    obs = obs.dropna(subset=["investment_product_id", "observation_date", "market_price"])
    obs = obs[obs["market_price"] > 0].copy()

    rows = []
    for pid, g in obs.groupby("investment_product_id"):
        g = g.sort_values("observation_date").copy()
        latest = g.iloc[-1]
        current = float(latest["market_price"])
        latest_date = latest["observation_date"]
        prices = g["market_price"].astype(float)

        ath = float(prices.max())
        atl = float(prices.min())
        returns = prices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()

        row = {
            "investment_product_id": pid,
            "latest_price": round(current, 2),
            "observation_count": len(g),
            "first_observation_date": g["observation_date"].min().date().isoformat(),
            "latest_observation_date": latest_date.date().isoformat(),
            "ath_price": round(ath, 2),
            "atl_price": round(atl, 2),
            "drawdown_from_ath": round(current / ath - 1, 4) if ath else np.nan,
            "annualized_volatility": round(float(returns.std() * np.sqrt(365)), 4) if len(returns) >= 2 else np.nan,
        }

        for window in [30, 90, 180, 365]:
            cutoff = latest_date - pd.Timedelta(days=window)
            recent = g[g["observation_date"] >= cutoff]
            row[f"ma_{window}d"] = round(float(recent["market_price"].mean()), 2) if not recent.empty else np.nan
            old = _price_at_or_before(g, cutoff)
            row[f"return_{window}d"] = round(current / old - 1, 4) if old and not np.isnan(old) else np.nan

        # Scores
        momentum_inputs = [row.get("return_30d"), row.get("return_90d"), row.get("return_180d")]
        momentum = 50
        for ret, weight in zip(momentum_inputs, [30, 45, 25]):
            if not pd.isna(ret):
                momentum += ret * weight
        row["trend_score"] = round(max(0, min(100, momentum)), 2)

        vol = row.get("annualized_volatility")
        if pd.isna(vol):
            row["volatility_score"] = 50
        elif vol < 0.20:
            row["volatility_score"] = 75
        elif vol < 0.40:
            row["volatility_score"] = 60
        elif vol < 0.70:
            row["volatility_score"] = 45
        else:
            row["volatility_score"] = 30

        row["history_confidence"] = round(min(100, len(g) / 12 * 100), 1)  # monthly snapshots: 12 months = high confidence
        rows.append(row)

    features = pd.DataFrame(rows)

    conn = get_connection()
    try:
        for _, r in features.iterrows():
            conn.execute(
                """
                INSERT INTO product_features (
                    investment_product_id, latest_price, observation_count,
                    first_observation_date, latest_observation_date, ath_price, atl_price,
                    drawdown_from_ath, return_30d, return_90d, return_180d, return_365d,
                    ma_30d, ma_90d, annualized_volatility, trend_score, volatility_score,
                    history_confidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(investment_product_id) DO UPDATE SET
                    latest_price=excluded.latest_price,
                    observation_count=excluded.observation_count,
                    first_observation_date=excluded.first_observation_date,
                    latest_observation_date=excluded.latest_observation_date,
                    ath_price=excluded.ath_price,
                    atl_price=excluded.atl_price,
                    drawdown_from_ath=excluded.drawdown_from_ath,
                    return_30d=excluded.return_30d,
                    return_90d=excluded.return_90d,
                    return_180d=excluded.return_180d,
                    return_365d=excluded.return_365d,
                    ma_30d=excluded.ma_30d,
                    ma_90d=excluded.ma_90d,
                    annualized_volatility=excluded.annualized_volatility,
                    trend_score=excluded.trend_score,
                    volatility_score=excluded.volatility_score,
                    history_confidence=excluded.history_confidence,
                    updated_at=CURRENT_TIMESTAMP
                """,
                tuple(r.get(c) for c in [
                    "investment_product_id","latest_price","observation_count","first_observation_date",
                    "latest_observation_date","ath_price","atl_price","drawdown_from_ath",
                    "return_30d","return_90d","return_180d","return_365d","ma_30d","ma_90d",
                    "annualized_volatility","trend_score","volatility_score","history_confidence"
                ]),
            )
        conn.commit()
    finally:
        conn.close()

    return features
