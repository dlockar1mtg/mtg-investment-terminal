from __future__ import annotations

from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

from terminal2.config import DB_FILE, EXPORT_DIR


def load_price_history():
    if not Path(DB_FILE).exists():
        raise FileNotFoundError(f"SQLite database not found: {DB_FILE}")

    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query(
            """
            SELECT
                po.observation_date,
                po.investment_product_id,
                po.tcgplayer_product_id,
                po.price_source,
                po.market_price,
                po.low_price,
                po.price_data_quality,
                p.box_name,
                p.set_name
            FROM price_observations po
            LEFT JOIN products p
                ON p.investment_product_id = po.investment_product_id
            WHERE po.market_price IS NOT NULL
              AND po.market_price > 0
            ORDER BY po.investment_product_id, po.observation_date
            """,
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        return df

    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["market_price"] = pd.to_numeric(df["market_price"], errors="coerce")
    df = df.dropna(subset=["observation_date", "investment_product_id", "market_price"])
    df = df.sort_values(["investment_product_id", "observation_date"]).copy()

    df["year"] = df["observation_date"].dt.year
    df["month"] = df["observation_date"].dt.month
    df["month_name"] = df["observation_date"].dt.strftime("%B")
    df["year_month"] = df["observation_date"].dt.to_period("M").astype(str)

    return df


def calculate_monthly_returns(df):
    if df.empty:
        return df

    rows = []

    for product_id, group in df.groupby("investment_product_id"):
        group = group.sort_values("observation_date").copy()

        # One price point per product-month. Since the backfill uses monthly snapshots,
        # this is usually already one row, but this makes it robust for daily data too.
        monthly = (
            group.sort_values("observation_date")
                 .groupby("year_month", as_index=False)
                 .tail(1)
                 .sort_values("observation_date")
                 .copy()
        )

        monthly["previous_price"] = monthly["market_price"].shift(1)
        monthly["monthly_return"] = (monthly["market_price"] / monthly["previous_price"]) - 1
        monthly["previous_observation_date"] = monthly["observation_date"].shift(1)

        rows.append(monthly)

    out = pd.concat(rows, ignore_index=True, sort=False)
    out = out.dropna(subset=["monthly_return"]).copy()
    out["monthly_return_pct"] = (out["monthly_return"] * 100).round(2)

    return out


def summarize_by_month(monthly_returns):
    if monthly_returns.empty:
        return pd.DataFrame()

    summary = (
        monthly_returns
        .groupby(["month", "month_name"], as_index=False)
        .agg(
            observations=("monthly_return", "count"),
            products=("investment_product_id", "nunique"),
            avg_return=("monthly_return", "mean"),
            median_return=("monthly_return", "median"),
            positive_rate=("monthly_return", lambda s: (s > 0).mean()),
            best_return=("monthly_return", "max"),
            worst_return=("monthly_return", "min"),
            avg_price=("market_price", "mean"),
        )
        .sort_values("month")
    )

    for col in ["avg_return", "median_return", "positive_rate", "best_return", "worst_return"]:
        summary[col + "_pct"] = (summary[col] * 100).round(2)

    summary["avg_price"] = summary["avg_price"].round(2)

    # Lower average return months can be candidate buying windows.
    summary["buy_timing_rank"] = summary["avg_return"].rank(method="dense", ascending=True).astype(int)

    return summary


def summarize_by_product_month(monthly_returns):
    if monthly_returns.empty:
        return pd.DataFrame()

    summary = (
        monthly_returns
        .groupby(["investment_product_id", "box_name", "month", "month_name"], as_index=False)
        .agg(
            observations=("monthly_return", "count"),
            avg_return=("monthly_return", "mean"),
            median_return=("monthly_return", "median"),
            positive_rate=("monthly_return", lambda s: (s > 0).mean()),
            best_return=("monthly_return", "max"),
            worst_return=("monthly_return", "min"),
        )
        .sort_values(["box_name", "month"])
    )

    for col in ["avg_return", "median_return", "positive_rate", "best_return", "worst_return"]:
        summary[col + "_pct"] = (summary[col] * 100).round(2)

    return summary


def summarize_by_set_age(monthly_returns):
    """
    A simple proxy for lifecycle seasonality:
    month number since first observed price in the database.
    """
    if monthly_returns.empty:
        return pd.DataFrame()

    df = monthly_returns.copy()
    first_month = df.groupby("investment_product_id")["observation_date"].transform("min")
    df["months_since_first_observed"] = (
        (df["observation_date"].dt.year - first_month.dt.year) * 12
        + (df["observation_date"].dt.month - first_month.dt.month)
    )

    summary = (
        df.groupby("months_since_first_observed", as_index=False)
        .agg(
            observations=("monthly_return", "count"),
            products=("investment_product_id", "nunique"),
            avg_return=("monthly_return", "mean"),
            median_return=("monthly_return", "median"),
            positive_rate=("monthly_return", lambda s: (s > 0).mean()),
        )
        .sort_values("months_since_first_observed")
    )

    for col in ["avg_return", "median_return", "positive_rate"]:
        summary[col + "_pct"] = (summary[col] * 100).round(2)

    return summary


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    history = load_price_history()
    if history.empty:
        print("No price observations found. Run terminal2_backfill_monthly.py first.")
        return

    monthly_returns = calculate_monthly_returns(history)
    month_summary = summarize_by_month(monthly_returns)
    product_month_summary = summarize_by_product_month(monthly_returns)
    lifecycle_summary = summarize_by_set_age(monthly_returns)

    files = {
        "seasonality_monthly_returns": EXPORT_DIR / "seasonality_monthly_returns.csv",
        "seasonality_by_month": EXPORT_DIR / "seasonality_by_month.csv",
        "seasonality_by_product_month": EXPORT_DIR / "seasonality_by_product_month.csv",
        "seasonality_by_lifecycle_month": EXPORT_DIR / "seasonality_by_lifecycle_month.csv",
    }

    monthly_returns.to_csv(files["seasonality_monthly_returns"], index=False)
    month_summary.to_csv(files["seasonality_by_month"], index=False)
    product_month_summary.to_csv(files["seasonality_by_product_month"], index=False)
    lifecycle_summary.to_csv(files["seasonality_by_lifecycle_month"], index=False)

    print("\nSeasonality analysis complete.")
    print(f"Products analyzed: {history['investment_product_id'].nunique()}")
    print(f"Monthly return observations: {len(monthly_returns)}")

    print("\nCalendar month summary:")
    cols = [
        "month",
        "month_name",
        "observations",
        "products",
        "avg_return_pct",
        "median_return_pct",
        "positive_rate_pct",
        "buy_timing_rank",
    ]
    if not month_summary.empty:
        print(month_summary[cols].to_string(index=False))

    print("\nFiles created:")
    for label, path in files.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
