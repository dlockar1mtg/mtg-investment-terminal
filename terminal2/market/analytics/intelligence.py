from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import numpy as np
import pandas as pd

from terminal2.db.module2_migration import migrate_module2
from terminal2.db.schema import get_connection


def _read(sql):
    connection = get_connection()
    try:
        return pd.read_sql_query(sql, connection)
    finally:
        connection.close()


def _latest_per_product(df, date_col="observation_date"):
    if df.empty:
        return df
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    return (
        out.sort_values(["investment_product_id", date_col])
           .groupby("investment_product_id", as_index=False)
           .tail(1)
           .reset_index(drop=True)
    )


def _score_supply(row):
    has_actual = any(pd.notna(row.get(c)) for c in [
        "listing_count", "seller_count", "inventory_units",
        "inventory_change_7d", "inventory_change_30d",
    ])
    if not has_actual:
        return 50.0, 0.0, "No supply source; neutral."

    score = 50.0
    listing = row.get("listing_count")
    sellers = row.get("seller_count")
    change7 = row.get("inventory_change_7d")
    change30 = row.get("inventory_change_30d")

    if pd.notna(listing):
        if listing <= 15:
            score += 20
        elif listing <= 40:
            score += 12
        elif listing >= 200:
            score -= 15
        elif listing >= 100:
            score -= 8

    if pd.notna(sellers):
        if sellers <= 5:
            score += 10
        elif sellers >= 50:
            score -= 8

    if pd.notna(change7):
        if change7 <= -0.15:
            score += 10
        elif change7 >= 0.15:
            score -= 8

    if pd.notna(change30):
        if change30 <= -0.25:
            score += 18
        elif change30 <= -0.08:
            score += 10
        elif change30 >= 0.25:
            score -= 15
        elif change30 >= 0.08:
            score -= 8

    confidence = row.get("supply_source_confidence")
    confidence = 60.0 if pd.isna(confidence) else float(confidence)
    return float(np.clip(score, 0, 100)), float(np.clip(confidence, 0, 100)), "Actual supply observations."


def _score_sales(row):
    has_actual = any(pd.notna(row.get(c)) for c in [
        "sales_7d", "sales_30d", "median_sold_price_30d",
        "sell_through_rate_30d", "average_days_to_sale",
    ])
    if not has_actual:
        return 50.0, 0.0, "No sales source; neutral."

    score = 50.0
    sales7 = row.get("sales_7d")
    sales30 = row.get("sales_30d")
    sell_through = row.get("sell_through_rate_30d")
    days = row.get("average_days_to_sale")

    if pd.notna(sales7):
        if sales7 >= 10:
            score += 15
        elif sales7 >= 4:
            score += 8
        elif sales7 <= 1:
            score -= 8

    if pd.notna(sales30):
        if sales30 >= 30:
            score += 15
        elif sales30 >= 10:
            score += 8
        elif sales30 <= 2:
            score -= 10

    if pd.notna(sell_through):
        if sell_through >= 0.35:
            score += 20
        elif sell_through >= 0.15:
            score += 10
        elif sell_through <= 0.03:
            score -= 15

    if pd.notna(days):
        if days <= 7:
            score += 10
        elif days >= 45:
            score -= 10

    confidence = row.get("sales_source_confidence")
    confidence = 60.0 if pd.isna(confidence) else float(confidence)
    return float(np.clip(score, 0, 100)), float(np.clip(confidence, 0, 100)), "Actual sales observations."


def _liquidity_proxy(row):
    spread = row.get("spread_pct")
    observations = row.get("observation_count")
    volatility = row.get("annualized_volatility")
    price = row.get("current_price")

    score = 55.0
    confidence = 35.0
    reasons = ["Price/history proxy"]

    if pd.notna(spread):
        confidence += 15
        if spread <= 0.05:
            score += 18
        elif spread <= 0.12:
            score += 8
        elif spread >= 0.35:
            score -= 20
        elif spread >= 0.20:
            score -= 10

    if pd.notna(observations):
        confidence += min(20, float(observations) / 2)
        if observations >= 24:
            score += 7
        elif observations < 6:
            score -= 8

    if pd.notna(volatility):
        confidence += 10
        if volatility <= 0.25:
            score += 8
        elif volatility >= 0.75:
            score -= 15
        elif volatility >= 0.50:
            score -= 8

    if pd.notna(price):
        if price >= 2500:
            score -= 12
        elif price >= 1000:
            score -= 6
        elif 150 <= price <= 600:
            score += 5

    return float(np.clip(score, 0, 100)), float(np.clip(confidence, 0, 80)), "; ".join(reasons)


def compute_market_intelligence():
    migrate_module2()

    products = _read("SELECT investment_product_id, box_name, set_name, product_type, asset_class FROM products")
    features = _read("SELECT * FROM product_features")
    scores = _read("SELECT * FROM investment_scores")
    prices = _read("""
        SELECT po.*, p.box_name, p.set_name, p.product_type, p.asset_class
        FROM price_observations po
        LEFT JOIN products p USING(investment_product_id)
        ORDER BY po.observation_date, po.id
    """)
    supply = _read("SELECT * FROM supply_observations")
    sales = _read("SELECT * FROM sales_observations")

    if products.empty:
        return pd.DataFrame()

    latest_prices = _latest_per_product(prices)
    latest_supply = _latest_per_product(supply)
    latest_sales = _latest_per_product(sales)

    base = products.copy()

    if not features.empty:
        base = base.merge(features, on="investment_product_id", how="left", suffixes=("", "_feature"))
    if not scores.empty:
        base = base.merge(scores, on="investment_product_id", how="left", suffixes=("", "_score"))
    if not latest_prices.empty:
        lp_cols = [
            "investment_product_id", "observation_date", "market_price", "low_price",
            "mid_price", "high_price", "price_data_quality", "created_at", "price_source"
        ]
        base = base.merge(latest_prices[[c for c in lp_cols if c in latest_prices.columns]], on="investment_product_id", how="left")
    if not latest_supply.empty:
        supply_cols = [
            "investment_product_id", "listing_count", "seller_count", "inventory_units",
            "inventory_change_7d", "inventory_change_30d", "source_confidence",
            "source_name"
        ]
        supply_latest = latest_supply[[c for c in supply_cols if c in latest_supply.columns]].rename(columns={
            "source_confidence": "supply_source_confidence",
            "source_name": "supply_source_name",
        })
        base = base.merge(supply_latest, on="investment_product_id", how="left")
    if not latest_sales.empty:
        sales_cols = [
            "investment_product_id", "sales_7d", "sales_30d", "median_sold_price_30d",
            "sell_through_rate_30d", "average_days_to_sale", "source_confidence",
            "source_name"
        ]
        sales_latest = latest_sales[[c for c in sales_cols if c in latest_sales.columns]].rename(columns={
            "source_confidence": "sales_source_confidence",
            "source_name": "sales_source_name",
        })
        base = base.merge(sales_latest, on="investment_product_id", how="left")

    base["current_price"] = pd.to_numeric(
        base.get("market_price", base.get("latest_price")), errors="coerce"
    )
    low = pd.to_numeric(base.get("low_price"), errors="coerce")
    high = pd.to_numeric(base.get("high_price"), errors="coerce")
    mid = pd.to_numeric(base.get("mid_price"), errors="coerce")
    comparison = high.fillna(mid).fillna(base["current_price"])
    base["spread_pct"] = np.where(
        low > 0,
        (comparison - low) / low,
        np.nan,
    )

    created = pd.to_datetime(base.get("created_at"), errors="coerce", utc=True)
    now = pd.Timestamp.now("UTC")
    base["price_freshness_hours"] = (now - created).dt.total_seconds() / 3600

    # Relative market returns.
    for horizon in ["30d", "90d"]:
        column = f"return_{horizon}"
        values = pd.to_numeric(base.get(column), errors="coerce")
        market_avg = float(values.mean()) if values.notna().any() else np.nan
        base[f"market_alpha_{horizon}"] = values - market_avg

    relative_components = []
    for col in ["market_alpha_30d", "market_alpha_90d"]:
        if col in base.columns:
            component = 50 + pd.to_numeric(base[col], errors="coerce").fillna(0) * 100
            relative_components.append(component.clip(0, 100))
    base["market_relative_strength"] = (
        pd.concat(relative_components, axis=1).mean(axis=1)
        if relative_components else 50.0
    )

    supply_results = base.apply(_score_supply, axis=1)
    sales_results = base.apply(_score_sales, axis=1)
    liquidity_results = base.apply(_liquidity_proxy, axis=1)

    base["supply_signal_score"] = [r[0] for r in supply_results]
    base["supply_confidence"] = [r[1] for r in supply_results]
    base["supply_basis"] = [r[2] for r in supply_results]

    base["sales_velocity_score"] = [r[0] for r in sales_results]
    base["sales_confidence"] = [r[1] for r in sales_results]
    base["sales_basis"] = [r[2] for r in sales_results]

    base["liquidity_score"] = [r[0] for r in liquidity_results]
    base["liquidity_confidence"] = [r[1] for r in liquidity_results]
    base["liquidity_basis"] = [r[2] for r in liquidity_results]

    history_conf = pd.to_numeric(base.get("history_confidence"), errors="coerce").fillna(0)
    price_quality = pd.to_numeric(base.get("price_data_quality"), errors="coerce").fillna(0)
    relative = pd.to_numeric(base["market_relative_strength"], errors="coerce").fillna(50)

    actual_supply_weight = base["supply_confidence"] / 100
    actual_sales_weight = base["sales_confidence"] / 100

    base["market_intelligence_score"] = (
        relative * 0.30
        + base["liquidity_score"] * 0.25
        + base["supply_signal_score"] * 0.20
        + base["sales_velocity_score"] * 0.20
        + price_quality * 0.05
    ).round(2)

    base["market_intelligence_confidence"] = (
        history_conf * 0.30
        + price_quality * 0.25
        + base["liquidity_confidence"] * 0.20
        + base["supply_confidence"] * 0.125
        + base["sales_confidence"] * 0.125
    ).clip(0, 100).round(2)

    base["signal_basis"] = np.select(
        [
            (base["supply_confidence"] > 0) & (base["sales_confidence"] > 0),
            base["supply_confidence"] > 0,
            base["sales_confidence"] > 0,
        ],
        [
            "Price history + actual supply + actual sales",
            "Price history + actual supply",
            "Price history + actual sales",
        ],
        default="Price history and spread proxy only",
    )

    connection = get_connection()
    try:
        for _, row in base.iterrows():
            connection.execute(
                """
                INSERT INTO market_intelligence (
                    investment_product_id, observation_date, current_price, spread_pct,
                    price_freshness_hours, supply_signal_score, supply_confidence,
                    liquidity_score, liquidity_confidence, sales_velocity_score,
                    sales_confidence, market_relative_strength, market_alpha_30d,
                    market_alpha_90d, market_intelligence_score,
                    market_intelligence_confidence, signal_basis, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(investment_product_id) DO UPDATE SET
                    observation_date=excluded.observation_date,
                    current_price=excluded.current_price,
                    spread_pct=excluded.spread_pct,
                    price_freshness_hours=excluded.price_freshness_hours,
                    supply_signal_score=excluded.supply_signal_score,
                    supply_confidence=excluded.supply_confidence,
                    liquidity_score=excluded.liquidity_score,
                    liquidity_confidence=excluded.liquidity_confidence,
                    sales_velocity_score=excluded.sales_velocity_score,
                    sales_confidence=excluded.sales_confidence,
                    market_relative_strength=excluded.market_relative_strength,
                    market_alpha_30d=excluded.market_alpha_30d,
                    market_alpha_90d=excluded.market_alpha_90d,
                    market_intelligence_score=excluded.market_intelligence_score,
                    market_intelligence_confidence=excluded.market_intelligence_confidence,
                    signal_basis=excluded.signal_basis,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    row.get("investment_product_id"),
                    str(row.get("observation_date")) if pd.notna(row.get("observation_date")) else None,
                    _scalar(row.get("current_price")),
                    _scalar(row.get("spread_pct")),
                    _scalar(row.get("price_freshness_hours")),
                    _scalar(row.get("supply_signal_score")),
                    _scalar(row.get("supply_confidence")),
                    _scalar(row.get("liquidity_score")),
                    _scalar(row.get("liquidity_confidence")),
                    _scalar(row.get("sales_velocity_score")),
                    _scalar(row.get("sales_confidence")),
                    _scalar(row.get("market_relative_strength")),
                    _scalar(row.get("market_alpha_30d")),
                    _scalar(row.get("market_alpha_90d")),
                    _scalar(row.get("market_intelligence_score")),
                    _scalar(row.get("market_intelligence_confidence")),
                    row.get("signal_basis"),
                ),
            )
        connection.commit()
    finally:
        connection.close()

    return base.sort_values(
        ["market_intelligence_score", "market_intelligence_confidence"],
        ascending=False,
    ).reset_index(drop=True)


def _scalar(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value
