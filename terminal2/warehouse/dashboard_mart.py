from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import sqlite3

import numpy as np
import pandas as pd

from terminal2.config import DB_FILE, ROOT_DIR
from terminal2.db.module1_migration import migrate_module1


DATA_DIR = Path(ROOT_DIR) / "data"
ANALYTICS_DIR = DATA_DIR / "analytics"
DASHBOARD_DIR = DATA_DIR / "dashboard"

CURRENT_DIR = ANALYTICS_DIR / "current"
HISTORY_DIR = ANALYTICS_DIR / "history"
REPORTS_DIR = ANALYTICS_DIR / "reports"
SNAPSHOTS_DIR = ANALYTICS_DIR / "snapshots"

PRODUCTS_DIR = DASHBOARD_DIR / "products"
MARKET_DIR = DASHBOARD_DIR / "market"
LIFECYCLE_DIR = DASHBOARD_DIR / "lifecycle"
PORTFOLIO_DIR = DASHBOARD_DIR / "portfolio"
SEASONALITY_DIR = DASHBOARD_DIR / "seasonality"
RESEARCH_DIR = DASHBOARD_DIR / "research"
ALERTS_DIR = DASHBOARD_DIR / "alerts"
EXECUTIVE_DIR = DASHBOARD_DIR / "executive"

ALL_DIRS = [
    CURRENT_DIR, HISTORY_DIR, REPORTS_DIR, SNAPSHOTS_DIR,
    PRODUCTS_DIR, MARKET_DIR, LIFECYCLE_DIR, PORTFOLIO_DIR,
    SEASONALITY_DIR, RESEARCH_DIR, ALERTS_DIR, EXECUTIVE_DIR,
]


def _ensure_dirs():
    for directory in ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def _connect():
    migrate_module1()
    if not Path(DB_FILE).exists():
        raise FileNotFoundError(f"Terminal SQLite database not found: {DB_FILE}")
    return sqlite3.connect(DB_FILE)


def _table_exists(connection, name):
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _query(connection, sql):
    try:
        return pd.read_sql_query(sql, connection)
    except Exception:
        return pd.DataFrame()


def _safe_write(df, path, columns=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy() if df is not None else pd.DataFrame()
    if columns:
        for column in columns:
            if column not in output.columns:
                output[column] = pd.NA
        output = output[columns]
    output.to_csv(path, index=False)
    return path, len(output)


def _latest_prices(price_history):
    if price_history.empty:
        return pd.DataFrame()
    df = price_history.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df = df.sort_values(["investment_product_id", "observation_date", "id"])
    return df.groupby("investment_product_id", as_index=False).tail(1).reset_index(drop=True)


def _product_type_group(value):
    text = str(value or "").lower()
    if "secret lair" in text:
        return "Secret Lair"
    if "collector" in text:
        return "Collector Booster Display"
    if "masters" in text:
        return "Masters Booster Display"
    if "draft" in text or "traditional" in text or "booster display" in text or "booster box" in text:
        return "Draft/Traditional Booster Display"
    return str(value or "Other")


def _build_base_tables(connection):
    products = _query(connection, "SELECT * FROM products")
    metadata = _query(connection, "SELECT * FROM product_metadata") if _table_exists(connection, "product_metadata") else pd.DataFrame()
    prices = _query(connection, """
        SELECT po.*, p.box_name, p.set_name, p.product_type, p.asset_class
        FROM price_observations po
        LEFT JOIN products p USING(investment_product_id)
        ORDER BY observation_date, investment_product_id
    """)
    features = _query(connection, "SELECT * FROM product_features")
    scores = _query(connection, "SELECT * FROM investment_scores")
    source_runs = _query(connection, "SELECT * FROM source_runs")
    return products, metadata, prices, features, scores, source_runs


def _build_product_summary(products, metadata, features, scores, latest):
    if products.empty:
        return pd.DataFrame()

    result = products.copy()
    if not metadata.empty:
        result = result.merge(metadata, on="investment_product_id", how="left", suffixes=("", "_metadata"))
    if not features.empty:
        result = result.merge(features, on="investment_product_id", how="left", suffixes=("", "_feature"))
    if not scores.empty:
        result = result.merge(scores, on="investment_product_id", how="left", suffixes=("", "_score"))
    if not latest.empty:
        latest_cols = [
            c for c in [
                "investment_product_id", "observation_date", "market_price", "low_price",
                "mid_price", "high_price", "price_source", "price_data_quality"
            ] if c in latest.columns
        ]
        result = result.merge(latest[latest_cols], on="investment_product_id", how="left", suffixes=("", "_latest"))

    result["product_type_group"] = result.get("product_type", pd.Series(index=result.index)).apply(_product_type_group)
    result["is_approved"] = result.get("approval_status", "").astype(str).str.lower().eq("approved")
    result["current_price"] = pd.to_numeric(
        result.get("current_price", result.get("market_price")), errors="coerce"
    )
    result["price_vs_target_pct"] = np.where(
        pd.to_numeric(result.get("target_buy_price"), errors="coerce") > 0,
        (result["current_price"] / pd.to_numeric(result.get("target_buy_price"), errors="coerce") - 1) * 100,
        np.nan,
    )
    return result


def _build_quality_scores(summary):
    if summary.empty:
        return pd.DataFrame()
    cols = [
        "investment_product_id", "box_name", "product_type_group", "price_data_quality",
        "history_confidence", "projection_confidence", "observation_count",
        "approval_status", "confidence", "source"
    ]
    out = summary[[c for c in cols if c in summary.columns]].copy()
    components = []
    for col in ["price_data_quality", "history_confidence", "projection_confidence", "confidence"]:
        if col in out.columns:
            components.append(pd.to_numeric(out[col], errors="coerce"))
    out["overall_data_quality_score"] = pd.concat(components, axis=1).mean(axis=1).round(2) if components else pd.NA
    return out


def _build_buy_zones(summary):
    cols = [
        "investment_product_id", "box_name", "product_type_group", "current_price",
        "target_buy_price", "price_vs_target_pct", "buy_signal", "rating",
        "investment_score", "risk_adjusted_score", "projection_confidence"
    ]
    return summary[[c for c in cols if c in summary.columns]].copy() if not summary.empty else pd.DataFrame(columns=cols)


def _build_rankings(summary):
    cols = [
        "investment_product_id", "box_name", "set_name", "product_type_group",
        "current_price", "investment_score", "risk_adjusted_score", "rating",
        "buy_signal", "target_buy_price", "expected_cagr", "projection_confidence",
        "mc_median_5yr", "mc_p05_5yr", "mc_p95_5yr", "prob_double", "prob_loss"
    ]
    out = summary[[c for c in cols if c in summary.columns]].copy()
    if "risk_adjusted_score" in out.columns:
        out = out.sort_values("risk_adjusted_score", ascending=False)
        out["overall_rank"] = range(1, len(out) + 1)
        if "product_type_group" in out.columns:
            out["asset_class_rank"] = out.groupby("product_type_group")["risk_adjusted_score"].rank(
                ascending=False, method="dense"
            ).astype("Int64")
    return out


def _build_lifecycle(summary):
    if summary.empty:
        return pd.DataFrame()

    out = summary.copy()
    release_source = out["release_date"] if "release_date" in out.columns else pd.Series(pd.NaT, index=out.index)
    first_source = out["first_observation_date"] if "first_observation_date" in out.columns else pd.Series(pd.NaT, index=out.index)
    release = pd.to_datetime(release_source, errors="coerce")
    first = pd.to_datetime(first_source, errors="coerce")
    basis = release.fillna(first)
    today = pd.Timestamp.now("UTC").tz_localize(None)
    out["months_since_release"] = (
        (today.year - basis.dt.year) * 12 + (today.month - basis.dt.month)
    ).astype("Int64")

    def stage(months):
        if pd.isna(months):
            return "Unknown"
        if months < 0:
            return "Pre-release"
        if months <= 3:
            return "Release / Early Supply"
        if months <= 9:
            return "Supply Peak / Price Discovery"
        if months <= 18:
            return "Stabilization"
        if months <= 36:
            return "Supply Contraction / Growth"
        if months <= 60:
            return "Scarcity"
        return "Legacy"

    out["lifecycle_stage"] = out["months_since_release"].apply(stage)
    cols = [
        "investment_product_id", "box_name", "product_type_group", "release_date",
        "months_since_release", "lifecycle_stage", "current_price", "ath_price",
        "atl_price", "drawdown_from_ath", "return_365d", "observation_count",
        "history_confidence"
    ]
    return out[[c for c in cols if c in out.columns]].copy()


def _build_seasonality(prices):
    if prices.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty

    df = prices.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["market_price"] = pd.to_numeric(df["market_price"], errors="coerce")
    df = df.dropna(subset=["observation_date", "investment_product_id", "market_price"])
    df["year_month"] = df["observation_date"].dt.to_period("M").astype(str)
    df["month"] = df["observation_date"].dt.month
    df["month_name"] = df["observation_date"].dt.strftime("%B")

    monthly = (
        df.sort_values("observation_date")
          .groupby(["investment_product_id", "year_month"], as_index=False)
          .tail(1)
          .sort_values(["investment_product_id", "observation_date"])
    )
    monthly["previous_price"] = monthly.groupby("investment_product_id")["market_price"].shift(1)
    monthly["monthly_return"] = monthly["market_price"] / monthly["previous_price"] - 1
    monthly = monthly.dropna(subset=["monthly_return"]).copy()
    monthly["monthly_return_pct"] = (monthly["monthly_return"] * 100).round(2)

    by_month = (
        monthly.groupby(["month", "month_name"], as_index=False)
        .agg(
            observations=("monthly_return", "count"),
            products=("investment_product_id", "nunique"),
            avg_return=("monthly_return", "mean"),
            median_return=("monthly_return", "median"),
            positive_rate=("monthly_return", lambda x: (x > 0).mean()),
            best_return=("monthly_return", "max"),
            worst_return=("monthly_return", "min"),
        )
        .sort_values("month")
    )
    for col in ["avg_return", "median_return", "positive_rate", "best_return", "worst_return"]:
        by_month[f"{col}_pct"] = (by_month[col] * 100).round(2)
    if not by_month.empty:
        by_month["buy_timing_rank"] = by_month["avg_return"].rank(ascending=True, method="dense").astype("Int64")

    by_product = (
        monthly.groupby(
            ["investment_product_id", "box_name", "product_type", "month", "month_name"],
            as_index=False,
        )
        .agg(
            observations=("monthly_return", "count"),
            avg_return=("monthly_return", "mean"),
            median_return=("monthly_return", "median"),
            positive_rate=("monthly_return", lambda x: (x > 0).mean()),
        )
    )
    for col in ["avg_return", "median_return", "positive_rate"]:
        by_product[f"{col}_pct"] = (by_product[col] * 100).round(2)

    by_asset = (
        monthly.assign(product_type_group=monthly.get("product_type", "").apply(_product_type_group))
        .groupby(["product_type_group", "month", "month_name"], as_index=False)
        .agg(
            observations=("monthly_return", "count"),
            products=("investment_product_id", "nunique"),
            avg_return=("monthly_return", "mean"),
            median_return=("monthly_return", "median"),
            positive_rate=("monthly_return", lambda x: (x > 0).mean()),
        )
    )
    for col in ["avg_return", "median_return", "positive_rate"]:
        by_asset[f"{col}_pct"] = (by_asset[col] * 100).round(2)

    return monthly, by_month, by_product, by_asset


def _build_market_indices(prices):
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = prices.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["market_price"] = pd.to_numeric(df["market_price"], errors="coerce")
    df = df.dropna(subset=["observation_date", "investment_product_id", "market_price"])
    df["product_type_group"] = df.get("product_type", "").apply(_product_type_group)

    monthly = (
        df.assign(year_month=df["observation_date"].dt.to_period("M").astype(str))
        .sort_values("observation_date")
        .groupby(["investment_product_id", "year_month"], as_index=False)
        .tail(1)
        .sort_values(["investment_product_id", "observation_date"])
    )
    monthly["product_return"] = monthly.groupby("investment_product_id")["market_price"].pct_change()

    index_rows = []
    for asset_name, group in [("Magic Sealed Market Index", monthly)] + list(monthly.groupby("product_type_group")):
        grouped = group.groupby("observation_date", as_index=False).agg(
            average_return=("product_return", "mean"),
            median_return=("product_return", "median"),
            products=("investment_product_id", "nunique"),
            average_price=("market_price", "mean"),
        )
        grouped["index_name"] = asset_name
        grouped["index_level"] = (100 * (1 + grouped["average_return"].fillna(0)).cumprod()).round(2)
        index_rows.append(grouped)

    indices = pd.concat(index_rows, ignore_index=True, sort=False) if index_rows else pd.DataFrame()

    breadth = monthly.groupby("observation_date", as_index=False).agg(
        products=("investment_product_id", "nunique"),
        advancing_products=("product_return", lambda x: (x > 0).sum()),
        declining_products=("product_return", lambda x: (x < 0).sum()),
        unchanged_products=("product_return", lambda x: (x == 0).sum()),
        average_return=("product_return", "mean"),
        median_return=("product_return", "median"),
    )
    breadth["advance_decline_ratio"] = np.where(
        breadth["declining_products"] > 0,
        breadth["advancing_products"] / breadth["declining_products"],
        np.nan,
    )
    return indices, breadth


def _build_alerts(summary):
    if summary.empty:
        return pd.DataFrame()

    rows = []
    for _, row in summary.iterrows():
        pid = row.get("investment_product_id")
        name = row.get("box_name")
        current = pd.to_numeric(pd.Series([row.get("current_price")]), errors="coerce").iloc[0]
        target = pd.to_numeric(pd.Series([row.get("target_buy_price")]), errors="coerce").iloc[0]
        signal = str(row.get("buy_signal") or "")
        score = pd.to_numeric(pd.Series([row.get("risk_adjusted_score")]), errors="coerce").iloc[0]
        dd = pd.to_numeric(pd.Series([row.get("drawdown_from_ath")]), errors="coerce").iloc[0]

        if pd.notna(current) and pd.notna(target) and target > 0 and current <= target:
            rows.append({
                "investment_product_id": pid, "box_name": name,
                "alert_type": "BUY_ZONE", "severity": "High",
                "alert_message": f"Current price {current:.2f} is at or below target {target:.2f}.",
            })
        if signal in {"Buy", "Strong Buy", "Accumulate"}:
            rows.append({
                "investment_product_id": pid, "box_name": name,
                "alert_type": "BUY_SIGNAL", "severity": "Medium",
                "alert_message": f"Model signal is {signal}.",
            })
        if pd.notna(score) and score >= 75:
            rows.append({
                "investment_product_id": pid, "box_name": name,
                "alert_type": "HIGH_SCORE", "severity": "Medium",
                "alert_message": f"Risk-adjusted score is {score:.2f}.",
            })
        if pd.notna(dd) and dd <= -0.20:
            rows.append({
                "investment_product_id": pid, "box_name": name,
                "alert_type": "DRAWDOWN", "severity": "Low",
                "alert_message": f"Price is {abs(dd) * 100:.1f}% below observed high.",
            })

    out = pd.DataFrame(rows)
    if not out.empty:
        out["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    return out


def _build_executive(summary, rankings, alerts, indices):
    generated = datetime.now(timezone.utc).isoformat()
    if summary.empty:
        return pd.DataFrame([{"generated_at_utc": generated, "product_count": 0}])

    current_source = summary["current_price"] if "current_price" in summary.columns else pd.Series(np.nan, index=summary.index)
    score_source = summary["risk_adjusted_score"] if "risk_adjusted_score" in summary.columns else pd.Series(np.nan, index=summary.index)
    current_prices = pd.to_numeric(current_source, errors="coerce")
    scores = pd.to_numeric(score_source, errors="coerce")
    dashboard_summary = pd.DataFrame([{
        "generated_at_utc": generated,
        "product_count": len(summary),
        "approved_product_count": int(summary["is_approved"].sum()) if "is_approved" in summary.columns else 0,
        "asset_class_count": summary.get("product_type_group", pd.Series(dtype=str)).nunique(),
        "products_with_prices": int(current_prices.notna().sum()),
        "average_current_price": round(float(current_prices.mean()), 2) if current_prices.notna().any() else np.nan,
        "total_market_value_one_each": round(float(current_prices.sum()), 2) if current_prices.notna().any() else np.nan,
        "average_risk_adjusted_score": round(float(scores.mean()), 2) if scores.notna().any() else np.nan,
        "buy_signal_count": int(summary["buy_signal"].isin(["Buy", "Strong Buy", "Accumulate"]).sum()) if "buy_signal" in summary.columns else 0,
        "active_alert_count": len(alerts),
        "latest_market_index_level": (
            float(indices[indices["index_name"] == "Magic Sealed Market Index"].sort_values("observation_date").tail(1)["index_level"].iloc[0])
            if not indices.empty and not indices[indices["index_name"] == "Magic Sealed Market Index"].empty else np.nan
        ),
    }])
    return dashboard_summary


def build_dashboard_warehouse(create_snapshot=True):
    _ensure_dirs()
    connection = _connect()
    try:
        products, metadata, prices, features, scores, source_runs = _build_base_tables(connection)
    finally:
        connection.close()

    latest = _latest_prices(prices)
    summary = _build_product_summary(products, metadata, features, scores, latest)
    quality = _build_quality_scores(summary)
    buy_zones = _build_buy_zones(summary)
    rankings = _build_rankings(summary)
    lifecycle = _build_lifecycle(summary)
    seasonality_returns, seasonality_month, seasonality_product, seasonality_asset = _build_seasonality(prices)
    indices, breadth = _build_market_indices(prices)
    alerts = _build_alerts(summary)
    executive = _build_executive(summary, rankings, alerts, indices)

    generated_at = datetime.now(timezone.utc)
    run_date = generated_at.date().isoformat()
    run_timestamp = generated_at.strftime("%Y%m%d_%H%M%S")

    manifest = []
    def write(label, df, path, columns=None):
        file_path, rows = _safe_write(df, path, columns)
        manifest.append({
            "dataset": label,
            "path": str(file_path.relative_to(DATA_DIR)),
            "rows": rows,
            "generated_at_utc": generated_at.isoformat(),
        })

    # Products
    write("product_master", products, PRODUCTS_DIR / "product_master.csv")
    write("product_metadata", metadata, PRODUCTS_DIR / "product_metadata.csv")
    write("current_prices", latest, PRODUCTS_DIR / "current_prices.csv")
    write("historical_prices", prices, PRODUCTS_DIR / "historical_prices.csv")
    write("investment_scores", scores, PRODUCTS_DIR / "investment_scores.csv")
    write("quality_scores", quality, PRODUCTS_DIR / "quality_scores.csv")
    write("buy_zones", buy_zones, PRODUCTS_DIR / "buy_zones.csv")
    write("product_rankings", rankings, PRODUCTS_DIR / "product_rankings.csv")
    write("product_summary", summary, PRODUCTS_DIR / "product_summary.csv")

    # Market
    write("magic_market_index", indices[indices.get("index_name", "") == "Magic Sealed Market Index"] if not indices.empty else pd.DataFrame(), MARKET_DIR / "magic_market_index.csv",
          ["observation_date", "average_return", "median_return", "products", "average_price", "index_name", "index_level"])
    write("asset_class_indices", indices[indices.get("index_name", "") != "Magic Sealed Market Index"] if not indices.empty else pd.DataFrame(), MARKET_DIR / "asset_class_indices.csv")
    for asset_label, filename in [
        ("Collector Booster Display", "collector_index.csv"),
        ("Draft/Traditional Booster Display", "draft_index.csv"),
        ("Masters Booster Display", "masters_index.csv"),
        ("Secret Lair", "secret_lair_index.csv"),
    ]:
        write(filename.replace(".csv", ""), indices[indices.get("index_name", "") == asset_label] if not indices.empty else pd.DataFrame(), MARKET_DIR / filename)
    write("market_breadth", breadth, MARKET_DIR / "market_breadth.csv")
    write("market_strength", breadth, MARKET_DIR / "market_strength.csv")
    write("source_health", source_runs, MARKET_DIR / "source_health.csv")
    write("supply_metrics", pd.DataFrame(), MARKET_DIR / "supply_metrics.csv",
          ["investment_product_id", "observation_date", "listing_count", "seller_count", "inventory_units", "inventory_change_7d", "inventory_change_30d", "confidence"])
    write("liquidity", pd.DataFrame(), MARKET_DIR / "liquidity.csv",
          ["investment_product_id", "observation_date", "sales_7d", "sales_30d", "sell_through_rate", "spread_pct", "liquidity_score", "confidence"])

    # Lifecycle
    write("lifecycle_stage", lifecycle, LIFECYCLE_DIR / "lifecycle_stage.csv")
    write("time_since_release", lifecycle, LIFECYCLE_DIR / "time_since_release.csv")
    write("bottom_predictions", pd.DataFrame(), LIFECYCLE_DIR / "bottom_predictions.csv",
          ["investment_product_id", "box_name", "estimated_bottom_date", "estimated_bottom_price", "bottom_probability", "confidence"])
    write("expected_bottom_dates", pd.DataFrame(), LIFECYCLE_DIR / "expected_bottom_dates.csv",
          ["investment_product_id", "box_name", "expected_bottom_date", "confidence"])
    write("recovery_curves", pd.DataFrame(), LIFECYCLE_DIR / "recovery_curves.csv",
          ["asset_class", "lifecycle_month", "average_indexed_price", "median_indexed_price", "products"])
    write("price_curve_models", pd.DataFrame(), LIFECYCLE_DIR / "price_curve_models.csv",
          ["asset_class", "model_version", "lifecycle_month", "expected_price_index", "lower_bound", "upper_bound"])

    # Seasonality
    write("seasonality_monthly_returns", seasonality_returns, SEASONALITY_DIR / "seasonality_monthly_returns.csv")
    write("seasonality_month", seasonality_month, SEASONALITY_DIR / "seasonality_month.csv",
          ["month", "month_name", "observations", "products", "avg_return", "median_return", "positive_rate", "best_return", "worst_return", "avg_return_pct", "median_return_pct", "positive_rate_pct", "best_return_pct", "worst_return_pct", "buy_timing_rank"])
    write("seasonality_product", seasonality_product, SEASONALITY_DIR / "seasonality_product.csv")
    write("seasonality_asset_class", seasonality_asset, SEASONALITY_DIR / "seasonality_asset_class.csv")
    best_buy = seasonality_month.sort_values("buy_timing_rank").head(3) if not seasonality_month.empty else pd.DataFrame()
    write("best_buy_month", best_buy, SEASONALITY_DIR / "best_buy_month.csv")
    write("release_month_effect", pd.DataFrame(), SEASONALITY_DIR / "release_month_effect.csv",
          ["release_month", "asset_class", "observations", "avg_3m_return", "avg_6m_return", "avg_12m_return"])

    # Research
    research_cols = [
        "investment_product_id", "box_name", "product_type_group", "current_price",
        "investment_score", "risk_adjusted_score", "expected_cagr", "projection_confidence",
        "mc_median_5yr", "mc_p05_5yr", "mc_p95_5yr", "prob_double", "prob_loss",
    ]
    write("expected_returns", summary[[c for c in research_cols if c in summary.columns]], RESEARCH_DIR / "expected_returns.csv")
    write("monte_carlo_summary", summary[[c for c in research_cols if c in summary.columns]], RESEARCH_DIR / "monte_carlo_summary.csv")
    write("confidence", quality, RESEARCH_DIR / "confidence.csv")
    write("factor_scores", summary[[c for c in [
        "investment_product_id", "box_name", "trend_score", "volatility_score",
        "history_confidence", "investment_score", "risk_adjusted_score"
    ] if c in summary.columns]], RESEARCH_DIR / "factor_scores.csv")
    write("analog_engine", pd.DataFrame(), RESEARCH_DIR / "analog_engine.csv",
          ["investment_product_id", "analog_product_id", "analog_box_name", "similarity_score", "analog_rank", "reason"])
    write("research_reports", pd.DataFrame(), RESEARCH_DIR / "research_reports.csv",
          ["investment_product_id", "box_name", "investment_thesis", "key_risks", "recommended_action", "generated_at_utc"])

    # Portfolio
    write("portfolio_optimizer", pd.DataFrame(), PORTFOLIO_DIR / "portfolio_optimizer.csv",
          ["portfolio_name", "investment_product_id", "box_name", "quantity", "unit_price", "allocation_pct", "expected_return", "risk"])
    write("efficient_frontier", pd.DataFrame(), PORTFOLIO_DIR / "efficient_frontier.csv",
          ["portfolio_id", "expected_return", "volatility", "sharpe_ratio"])
    write("risk_matrix", pd.DataFrame(), PORTFOLIO_DIR / "risk_matrix.csv",
          ["investment_product_id", "box_name", "volatility", "downside_risk", "liquidity_risk", "reprint_risk", "overall_risk"])
    write("correlation_matrix", pd.DataFrame(), PORTFOLIO_DIR / "correlation_matrix.csv",
          ["product_a_id", "product_b_id", "correlation"])
    write("recommended_portfolios", pd.DataFrame(), PORTFOLIO_DIR / "recommended_portfolios.csv",
          ["portfolio_name", "risk_profile", "budget", "expected_return", "expected_volatility", "product_count"])
    write("allocation_breakdown", pd.DataFrame(), PORTFOLIO_DIR / "allocation_breakdown.csv",
          ["portfolio_name", "asset_class", "allocation_pct", "allocation_value"])

    # Alerts
    write("buy_alerts", alerts[alerts.get("alert_type", "") == "BUY_ZONE"] if not alerts.empty else pd.DataFrame(), ALERTS_DIR / "buy_alerts.csv")
    write("price_breakouts", pd.DataFrame(), ALERTS_DIR / "price_breakouts.csv",
          ["investment_product_id", "box_name", "observation_date", "breakout_type", "current_price", "threshold"])
    write("bottom_alerts", alerts[alerts.get("alert_type", "") == "DRAWDOWN"] if not alerts.empty else pd.DataFrame(), ALERTS_DIR / "bottom_alerts.csv")
    write("inventory_alerts", pd.DataFrame(), ALERTS_DIR / "inventory_alerts.csv",
          ["investment_product_id", "box_name", "observation_date", "inventory_change_pct", "severity", "message"])
    write("market_events", pd.DataFrame(), ALERTS_DIR / "market_events.csv",
          ["event_date", "event_type", "title", "description", "affected_product_id", "source"])

    # Executive
    write("dashboard_summary", executive, EXECUTIVE_DIR / "dashboard_summary.csv")
    write("top_opportunities", rankings.head(10), EXECUTIVE_DIR / "top_opportunities.csv")
    if not rankings.empty and "risk_adjusted_score" in rankings.columns:
        worst_values = rankings.tail(10).sort_values("risk_adjusted_score")
    else:
        worst_values = rankings
    write("worst_values", worst_values, EXECUTIVE_DIR / "worst_values.csv")
    high_conf = rankings.sort_values("projection_confidence", ascending=False).head(10) if "projection_confidence" in rankings.columns else pd.DataFrame()
    write("highest_confidence", high_conf, EXECUTIVE_DIR / "highest_confidence.csv")
    if not rankings.empty and "buy_signal" in rankings.columns:
        watchlist = rankings[rankings["buy_signal"].isin(["Watch", "Accumulate", "Buy", "Strong Buy"])]
    else:
        watchlist = pd.DataFrame()
    write("watchlist", watchlist, EXECUTIVE_DIR / "watchlist.csv")
    if "release_date" in summary.columns:
        release = pd.to_datetime(summary["release_date"], errors="coerce")
        new_products = summary[release >= (pd.Timestamp.now("UTC").tz_localize(None) - pd.Timedelta(days=365))]
    else:
        new_products = pd.DataFrame()
    write("new_products", new_products, EXECUTIVE_DIR / "new_products.csv")
    write("daily_summary", executive, EXECUTIVE_DIR / "daily_summary.csv")

    # Current consolidated layer
    write("current_product_summary", summary, CURRENT_DIR / "product_summary.csv")
    write("current_rankings", rankings, CURRENT_DIR / "rankings.csv")
    write("current_alerts", alerts, CURRENT_DIR / "alerts.csv")
    write("current_market_indices", indices, CURRENT_DIR / "market_indices.csv",
          ["observation_date", "average_return", "median_return", "products", "average_price", "index_name", "index_level"])
    write("current_lifecycle", lifecycle, CURRENT_DIR / "lifecycle.csv")
    write("current_seasonality", seasonality_month, CURRENT_DIR / "seasonality.csv",
          ["month", "month_name", "observations", "products", "avg_return", "median_return", "positive_rate", "best_return", "worst_return", "avg_return_pct", "median_return_pct", "positive_rate_pct", "best_return_pct", "worst_return_pct", "buy_timing_rank"])

    manifest_df = pd.DataFrame(manifest)
    _safe_write(manifest_df, DASHBOARD_DIR / "dataset_manifest.csv")
    _safe_write(manifest_df, ANALYTICS_DIR / "dataset_manifest.csv")

    schema_rows = []
    for item in manifest:
        file_path = DATA_DIR / item["path"]
        try:
            sample = pd.read_csv(file_path, nrows=5)
            for column in sample.columns:
                schema_rows.append({
                    "dataset": item["dataset"],
                    "path": item["path"],
                    "column_name": column,
                    "inferred_dtype": str(sample[column].dtype),
                })
        except Exception:
            pass
    _safe_write(pd.DataFrame(schema_rows), DASHBOARD_DIR / "data_dictionary.csv")

    if create_snapshot:
        daily_dir = HISTORY_DIR / run_date
        daily_dir.mkdir(parents=True, exist_ok=True)
        for source_file, target_name in [
            (CURRENT_DIR / "product_summary.csv", "product_summary.csv"),
            (CURRENT_DIR / "rankings.csv", "rankings.csv"),
            (CURRENT_DIR / "alerts.csv", "alerts.csv"),
            (CURRENT_DIR / "market_indices.csv", "market_indices.csv"),
            (CURRENT_DIR / "lifecycle.csv", "lifecycle.csv"),
            (CURRENT_DIR / "seasonality.csv", "seasonality.csv"),
        ]:
            if source_file.exists():
                shutil.copy2(source_file, daily_dir / target_name)

        timestamp_dir = SNAPSHOTS_DIR / run_timestamp
        timestamp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DASHBOARD_DIR / "dataset_manifest.csv", timestamp_dir / "dataset_manifest.csv")
        shutil.copy2(EXECUTIVE_DIR / "dashboard_summary.csv", timestamp_dir / "dashboard_summary.csv")
        shutil.copy2(EXECUTIVE_DIR / "top_opportunities.csv", timestamp_dir / "top_opportunities.csv")

    status = {
        "generated_at_utc": generated_at.isoformat(),
        "database": str(DB_FILE),
        "datasets_created": len(manifest),
        "product_rows": len(summary),
        "historical_price_rows": len(prices),
        "alert_rows": len(alerts),
        "snapshot_date": run_date,
    }
    (DASHBOARD_DIR / "warehouse_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return manifest_df, status
