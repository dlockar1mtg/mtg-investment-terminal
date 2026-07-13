from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from terminal2.db.loaders import load_price_observations_df
from terminal2.db.schema import get_connection, init_db
from terminal2.features.price_features import compute_price_features
from terminal2.history.contracts import get_historical_contract
from terminal2.warehouse_core import DashboardPublisher, Warehouse


def _load_product_features() -> pd.DataFrame:
    init_db()
    connection = get_connection()
    try:
        return pd.read_sql_query(
            """
            SELECT pf.*, p.box_name, p.set_name, p.product_type
            FROM product_features pf
            LEFT JOIN products p
              ON p.investment_product_id = pf.investment_product_id
            ORDER BY pf.history_confidence DESC, pf.observation_count DESC
            """,
            connection,
        )
    finally:
        connection.close()


def _clean_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(
            columns=[
                "observation_date",
                "investment_product_id",
                "tcgplayer_product_id",
                "price_source",
                "market_price",
                "low_price",
                "mid_price",
                "high_price",
                "price_data_quality",
                "source_run_id",
                "box_name",
                "set_name",
                "product_type",
            ]
        )

    df = prices.copy()
    df["observation_date"] = pd.to_datetime(
        df["observation_date"], errors="coerce"
    )
    for column in [
        "market_price",
        "low_price",
        "mid_price",
        "high_price",
        "price_data_quality",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(
        subset=[
            "observation_date",
            "investment_product_id",
            "price_source",
            "market_price",
        ]
    )
    df = df[df["market_price"] > 0].copy()
    df["observation_date"] = (
        df["observation_date"].dt.date.astype(str)
    )

    key = [
        "observation_date",
        "investment_product_id",
        "price_source",
    ]
    df = (
        df.sort_values(key + ["price_data_quality"])
        .drop_duplicates(key, keep="last")
        .sort_values(key)
        .reset_index(drop=True)
    )
    return df


def _monthly_history(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(
            columns=[
                "year_month",
                "observation_date",
                "investment_product_id",
                "price_source",
                "market_price",
            ]
        )

    df = prices.copy()
    parsed = pd.to_datetime(df["observation_date"], errors="coerce")
    df["year_month"] = parsed.dt.to_period("M").astype(str)
    df["_parsed_date"] = parsed

    key = [
        "year_month",
        "investment_product_id",
        "price_source",
    ]
    monthly = (
        df.sort_values(key + ["_parsed_date"])
        .groupby(key, as_index=False)
        .tail(1)
        .drop(columns=["_parsed_date"])
        .sort_values(key)
        .reset_index(drop=True)
    )
    return monthly


def _historical_returns(monthly: pd.DataFrame) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame(
            columns=[
                "year_month",
                "investment_product_id",
                "price_source",
                "market_price",
                "previous_price",
                "monthly_return",
                "monthly_return_pct",
            ]
        )

    df = monthly.copy()
    df = df.sort_values(
        [
            "investment_product_id",
            "price_source",
            "year_month",
        ]
    )
    groups = df.groupby(
        ["investment_product_id", "price_source"],
        dropna=False,
    )
    df["previous_price"] = groups["market_price"].shift(1)
    df["monthly_return"] = (
        df["market_price"] / df["previous_price"]
    ) - 1
    df["monthly_return"] = df["monthly_return"].replace(
        [np.inf, -np.inf], np.nan
    )
    df["monthly_return_pct"] = (
        df["monthly_return"] * 100
    ).round(2)
    return df.dropna(subset=["monthly_return"]).reset_index(drop=True)


def _coverage(prices: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "investment_product_id",
        "box_name",
        "set_name",
        "product_type",
        "observation_count",
        "first_observation_date",
        "latest_observation_date",
        "history_span_days",
        "source_count",
        "average_price_data_quality",
        "coverage_status",
    ]
    if prices.empty:
        return pd.DataFrame(columns=columns)

    df = prices.copy()
    df["_date"] = pd.to_datetime(
        df["observation_date"], errors="coerce"
    )
    grouped = (
        df.groupby("investment_product_id", as_index=False)
        .agg(
            box_name=("box_name", "first"),
            set_name=("set_name", "first"),
            product_type=("product_type", "first"),
            observation_count=("market_price", "count"),
            first_observation_date=("_date", "min"),
            latest_observation_date=("_date", "max"),
            source_count=("price_source", "nunique"),
            average_price_data_quality=(
                "price_data_quality",
                "mean",
            ),
        )
    )
    grouped["history_span_days"] = (
        grouped["latest_observation_date"]
        - grouped["first_observation_date"]
    ).dt.days
    grouped["first_observation_date"] = (
        grouped["first_observation_date"].dt.date.astype(str)
    )
    grouped["latest_observation_date"] = (
        grouped["latest_observation_date"].dt.date.astype(str)
    )
    grouped["average_price_data_quality"] = (
        grouped["average_price_data_quality"].round(2)
    )
    grouped["coverage_status"] = np.select(
        [
            (grouped["observation_count"] >= 18)
            & (grouped["history_span_days"] >= 365),
            (grouped["observation_count"] >= 12)
            & (grouped["history_span_days"] >= 180),
            grouped["observation_count"] >= 6,
        ],
        ["Strong", "Moderate", "Limited"],
        default="Insufficient",
    )
    return grouped[columns]


def _source_quality(prices: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "price_source",
        "observation_count",
        "product_count",
        "first_observation_date",
        "latest_observation_date",
        "average_price_data_quality",
        "missing_market_price_count",
    ]
    if prices.empty:
        return pd.DataFrame(columns=columns)

    df = prices.copy()
    df["_date"] = pd.to_datetime(
        df["observation_date"], errors="coerce"
    )
    summary = (
        df.groupby("price_source", as_index=False)
        .agg(
            observation_count=("market_price", "count"),
            product_count=("investment_product_id", "nunique"),
            first_observation_date=("_date", "min"),
            latest_observation_date=("_date", "max"),
            average_price_data_quality=(
                "price_data_quality",
                "mean",
            ),
            missing_market_price_count=(
                "market_price",
                lambda series: int(series.isna().sum()),
            ),
        )
    )
    summary["first_observation_date"] = (
        summary["first_observation_date"].dt.date.astype(str)
    )
    summary["latest_observation_date"] = (
        summary["latest_observation_date"].dt.date.astype(str)
    )
    summary["average_price_data_quality"] = (
        summary["average_price_data_quality"].round(2)
    )
    return summary[columns]


def _historical_summary(
    prices: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    if prices.empty:
        return pd.DataFrame(
            [
                {
                    "snapshot_date": snapshot_date,
                    "observation_count": 0,
                    "product_count": 0,
                    "source_count": 0,
                    "first_observation_date": "",
                    "latest_observation_date": "",
                    "strong_coverage_products": 0,
                    "moderate_coverage_products": 0,
                    "limited_coverage_products": 0,
                    "insufficient_coverage_products": 0,
                }
            ]
        )

    status_counts = (
        coverage["coverage_status"].value_counts()
        if not coverage.empty
        else pd.Series(dtype="int64")
    )
    return pd.DataFrame(
        [
            {
                "snapshot_date": snapshot_date,
                "observation_count": int(len(prices)),
                "product_count": int(
                    prices["investment_product_id"].nunique()
                ),
                "source_count": int(
                    prices["price_source"].nunique()
                ),
                "first_observation_date": str(
                    prices["observation_date"].min()
                ),
                "latest_observation_date": str(
                    prices["observation_date"].max()
                ),
                "strong_coverage_products": int(
                    status_counts.get("Strong", 0)
                ),
                "moderate_coverage_products": int(
                    status_counts.get("Moderate", 0)
                ),
                "limited_coverage_products": int(
                    status_counts.get("Limited", 0)
                ),
                "insufficient_coverage_products": int(
                    status_counts.get("Insufficient", 0)
                ),
            }
        ]
    )


def build_historical_datasets(
    *,
    recompute_features: bool = False,
) -> dict[str, pd.DataFrame]:
    if recompute_features:
        compute_price_features()

    prices = _clean_prices(load_price_observations_df())
    monthly = _monthly_history(prices)
    returns = _historical_returns(monthly)
    features = _load_product_features()
    coverage = _coverage(prices)
    source_quality = _source_quality(prices)
    summary = _historical_summary(prices, coverage)

    return {
        "historical_prices": prices,
        "monthly_price_history": monthly,
        "historical_returns": returns,
        "historical_price_features": features,
        "historical_coverage": coverage,
        "historical_source_quality": source_quality,
        "historical_summary": summary,
    }


def publish_historical_datasets(
    datasets: dict[str, pd.DataFrame],
    *,
    warehouse: Warehouse | None = None,
):
    publisher = DashboardPublisher(warehouse or Warehouse())
    batch = [
        (
            datasets[name],
            get_historical_contract(name).definition(),
        )
        for name in datasets
    ]
    return publisher.publish_many(
        batch,
        message="Terminal 2.5.3 historical intelligence publication",
    )


def publish_historical_intelligence(
    *,
    warehouse: Warehouse | None = None,
    recompute_features: bool = False,
) -> dict:
    datasets = build_historical_datasets(
        recompute_features=recompute_features
    )
    results = publish_historical_datasets(
        datasets,
        warehouse=warehouse,
    )
    return {
        "datasets": len(results),
        "historical_price_rows": len(
            datasets["historical_prices"]
        ),
        "monthly_price_rows": len(
            datasets["monthly_price_history"]
        ),
        "historical_return_rows": len(
            datasets["historical_returns"]
        ),
        "coverage_rows": len(
            datasets["historical_coverage"]
        ),
        "source_quality_rows": len(
            datasets["historical_source_quality"]
        ),
    }
