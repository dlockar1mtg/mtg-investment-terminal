from __future__ import annotations

import numpy as np
import pandas as pd

from terminal2.db.schema import get_connection, init_db


def _scalar(row, col, default=None):
    """
    Always return a SQLite-bindable scalar value.
    Prevents pandas Series from being passed into sqlite3 parameters.
    """
    try:
        value = row[col]
    except Exception:
        return default

    if isinstance(value, pd.Series):
        value = value.iloc[0] if len(value) else default

    if pd.isna(value):
        return default

    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)

    return value


def score_from_features():
    init_db()
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            """
            SELECT
                p.investment_product_id,
                p.box_name,
                p.set_name,
                p.product_type,
                f.latest_price,
                f.observation_count,
                f.first_observation_date,
                f.latest_observation_date,
                f.ath_price,
                f.atl_price,
                f.drawdown_from_ath,
                f.return_30d,
                f.return_90d,
                f.return_180d,
                f.return_365d,
                f.ma_30d,
                f.ma_90d,
                f.annualized_volatility,
                f.trend_score,
                f.volatility_score,
                f.history_confidence
            FROM products p
            LEFT JOIN product_features f ON f.investment_product_id = p.investment_product_id
            """,
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        return df

    df["latest_price"] = pd.to_numeric(
        df["latest_price"],
        errors="coerce",
    )
    df = df[df["latest_price"].gt(0)].copy()

    if df.empty:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM investment_scores")
            conn.commit()
        finally:
            conn.close()
        return df

    latest = df["latest_price"]
    trend = pd.to_numeric(df["trend_score"], errors="coerce").fillna(50)
    vol_score = pd.to_numeric(df["volatility_score"], errors="coerce").fillna(50)
    hist_conf = pd.to_numeric(df["history_confidence"], errors="coerce").fillna(0)
    dd = pd.to_numeric(df["drawdown_from_ath"], errors="coerce").fillna(0)

    entry = 50 + ((-dd).clip(0, 0.35) * 80)
    entry = entry.clip(0, 100)

    name = df["box_name"].fillna("").str.lower()
    quality = pd.Series(50, index=df.index, dtype=float)
    quality += name.str.contains("lord of the rings").astype(int) * 25
    quality += name.str.contains("final fantasy").astype(int) * 18
    quality += name.str.contains("double masters").astype(int) * 15
    quality += name.str.contains("kamigawa").astype(int) * 14
    quality += name.str.contains("modern horizons").astype(int) * 12
    quality += name.str.contains("commander masters").astype(int) * 10
    quality += name.str.contains("universes beyond").astype(int) * 8
    quality = quality.clip(0, 100)

    score = (
        quality * 0.30 +
        trend * 0.20 +
        vol_score * 0.15 +
        entry * 0.15 +
        hist_conf * 0.20
    ).round(2)

    risk_adjusted = (score - ((100 - vol_score) * 0.05)).round(2)
    target = (latest * 0.82).round(2)

    expected_cagr = (
        0.06 +
        (score / 100) * 0.12 +
        (trend - 50) / 100 * 0.04
    ).clip(0.02, 0.30).round(4)

    df["investment_score"] = score
    df["risk_adjusted_score"] = risk_adjusted
    df["rating"] = pd.cut(
        risk_adjusted,
        bins=[-999, 55, 65, 75, 85, 999],
        labels=["Avoid", "Speculative", "Watch", "Accumulate", "Buy"],
    ).astype(str)
    df["buy_signal"] = np.where(risk_adjusted >= 80, "Buy", np.where(risk_adjusted >= 70, "Watch", "Wait"))
    df["target_buy_price"] = target
    df["expected_cagr"] = expected_cagr
    df["projection_confidence"] = hist_conf.clip(0, 95)
    df["mc_median_5yr"] = (latest * (1 + expected_cagr) ** 5).round(2)
    df["mc_p05_5yr"] = (df["mc_median_5yr"] * 0.55).round(2)
    df["mc_p95_5yr"] = (df["mc_median_5yr"] * 1.85).round(2)
    df["prob_double"] = (0.10 + (score / 100) * 0.30).round(4)
    df["prob_loss"] = (0.45 - (score / 100) * 0.25).clip(0.05, 0.50).round(4)

    eligible_ids = (
        df["investment_product_id"]
        .dropna()
        .astype(str)
        .tolist()
    )

    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in eligible_ids)

        conn.execute(
            f"""
            DELETE FROM investment_scores
            WHERE investment_product_id NOT IN ({placeholders})
            """,
            eligible_ids,
        )

        for _, r in df.iterrows():
            params = (
                _scalar(r, "investment_product_id"),
                _scalar(r, "latest_price", 0.0),
                _scalar(r, "investment_score", 0.0),
                _scalar(r, "risk_adjusted_score", 0.0),
                _scalar(r, "rating", "Unknown"),
                _scalar(r, "buy_signal", "Watch"),
                _scalar(r, "target_buy_price", 0.0),
                _scalar(r, "expected_cagr", 0.0),
                _scalar(r, "projection_confidence", 0.0),
                _scalar(r, "mc_median_5yr", 0.0),
                _scalar(r, "mc_p05_5yr", 0.0),
                _scalar(r, "mc_p95_5yr", 0.0),
                _scalar(r, "prob_double", 0.0),
                _scalar(r, "prob_loss", 0.0),
            )

            conn.execute(
                """
                INSERT INTO investment_scores (
                    investment_product_id, current_price, investment_score,
                    risk_adjusted_score, rating, buy_signal, target_buy_price,
                    expected_cagr, projection_confidence, mc_median_5yr, mc_p05_5yr,
                    mc_p95_5yr, prob_double, prob_loss, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(investment_product_id) DO UPDATE SET
                    current_price=excluded.current_price,
                    investment_score=excluded.investment_score,
                    risk_adjusted_score=excluded.risk_adjusted_score,
                    rating=excluded.rating,
                    buy_signal=excluded.buy_signal,
                    target_buy_price=excluded.target_buy_price,
                    expected_cagr=excluded.expected_cagr,
                    projection_confidence=excluded.projection_confidence,
                    mc_median_5yr=excluded.mc_median_5yr,
                    mc_p05_5yr=excluded.mc_p05_5yr,
                    mc_p95_5yr=excluded.mc_p95_5yr,
                    prob_double=excluded.prob_double,
                    prob_loss=excluded.prob_loss,
                    updated_at=CURRENT_TIMESTAMP
                """,
                params,
            )
        conn.commit()
    finally:
        conn.close()

    return df.sort_values("risk_adjusted_score", ascending=False)
