from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd

from terminal2.db.module2_migration import migrate_module2
from terminal2.db.schema import get_connection


def _series(df, column, default=None):
    """Return an index-aligned Series even when a column is absent."""
    if column in df.columns:
        return df[column]
    return pd.Series(default, index=df.index, dtype="object")




def _scalar(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _read(sql):
    connection = get_connection()
    try:
        return pd.read_sql_query(sql, connection)
    finally:
        connection.close()


def compute_source_health():
    migrate_module2()
    products = _read("SELECT COUNT(*) AS n FROM products")
    total_products = int(products["n"].iloc[0]) if not products.empty else 0
    prices = _read("SELECT * FROM price_observations")
    runs = _read("SELECT * FROM source_runs")

    rows = []
    today = pd.Timestamp.now("UTC").date().isoformat()

    source_names = set(prices.get("price_source", pd.Series(dtype=str)).dropna().astype(str))
    source_names.update(runs.get("source_name", pd.Series(dtype=str)).dropna().astype(str))

    for source in sorted(source_names):
        p = prices[prices["price_source"].astype(str) == source].copy() if not prices.empty else pd.DataFrame()
        r = runs[runs["source_name"].astype(str) == source].copy() if not runs.empty else pd.DataFrame()

        if not p.empty:
            created = pd.to_datetime(p["created_at"], errors="coerce", utc=True)
            avg_age = ((pd.Timestamp.now("UTC") - created).dt.total_seconds() / 3600).mean()
            covered = p["investment_product_id"].nunique()
        else:
            avg_age = np.nan
            covered = 0

        success_runs = int((r.get("status", "").astype(str).str.lower() == "success").sum()) if not r.empty else 0
        failed_runs = int((r.get("status", "").astype(str).str.lower() == "failed").sum()) if not r.empty else 0
        total_runs = success_runs + failed_runs
        success_rate = success_runs / total_runs if total_runs else np.nan
        coverage = covered / total_products if total_products else 0

        score = 50.0
        if pd.notna(success_rate):
            score += (success_rate - 0.5) * 40
        score += min(25, coverage * 25)
        if pd.notna(avg_age):
            if avg_age <= 24:
                score += 15
            elif avg_age >= 168:
                score -= 20
            elif avg_age >= 72:
                score -= 10

        score = float(np.clip(score, 0, 100))
        status = "Healthy" if score >= 75 else "Watch" if score >= 55 else "Degraded"

        rows.append({
            "snapshot_date": today,
            "source_name": source,
            "latest_success_at": r.loc[r.get("status", "").astype(str).str.lower() == "success", "run_finished_at"].max() if not r.empty else None,
            "latest_failure_at": r.loc[r.get("status", "").astype(str).str.lower() == "failed", "run_finished_at"].max() if not r.empty else None,
            "success_runs": success_runs,
            "failed_runs": failed_runs,
            "success_rate": round(success_rate, 4) if pd.notna(success_rate) else None,
            "records_processed": int(pd.to_numeric(r.get("records_processed"), errors="coerce").fillna(0).sum()) if not r.empty else len(p),
            "average_price_age_hours": round(float(avg_age), 2) if pd.notna(avg_age) else None,
            "products_covered": covered,
            "coverage_pct": round(coverage * 100, 2),
            "source_health_score": round(score, 2),
            "status": status,
        })

    out = pd.DataFrame(rows)
    connection = get_connection()
    try:
        for _, row in out.iterrows():
            connection.execute(
                """
                INSERT INTO source_health_history (
                    snapshot_date, source_name, latest_success_at, latest_failure_at,
                    success_runs, failed_runs, success_rate, records_processed,
                    average_price_age_hours, products_covered, coverage_pct,
                    source_health_score, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(snapshot_date, source_name) DO UPDATE SET
                    latest_success_at=excluded.latest_success_at,
                    latest_failure_at=excluded.latest_failure_at,
                    success_runs=excluded.success_runs,
                    failed_runs=excluded.failed_runs,
                    success_rate=excluded.success_rate,
                    records_processed=excluded.records_processed,
                    average_price_age_hours=excluded.average_price_age_hours,
                    products_covered=excluded.products_covered,
                    coverage_pct=excluded.coverage_pct,
                    source_health_score=excluded.source_health_score,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                tuple(_scalar(row.get(c)) for c in [
                    "snapshot_date","source_name","latest_success_at","latest_failure_at",
                    "success_runs","failed_runs","success_rate","records_processed",
                    "average_price_age_hours","products_covered","coverage_pct",
                    "source_health_score","status"
                ]),
            )
        connection.commit()
    finally:
        connection.close()
    return out



def _products_updated_today(prices):
    if prices is None or prices.empty:
        return 0
    if "observation_date" not in prices.columns or "investment_product_id" not in prices.columns:
        return 0

    dates = pd.to_datetime(prices["observation_date"], errors="coerce")
    mask = dates.dt.date == pd.Timestamp.now("UTC").date()
    return int(prices.loc[mask, "investment_product_id"].nunique())

def compute_market_health():
    migrate_module2()
    products = _read("SELECT * FROM products")
    features = _read("SELECT * FROM product_features")
    scores = _read("SELECT * FROM investment_scores")
    intelligence = _read("SELECT * FROM market_intelligence")
    prices = _read("SELECT * FROM price_observations")

    summary = products.copy()
    if not features.empty:
        summary = summary.merge(features, on="investment_product_id", how="left")
    if not scores.empty:
        summary = summary.merge(scores, on="investment_product_id", how="left")
    if not intelligence.empty:
        summary = summary.merge(intelligence, on="investment_product_id", how="left", suffixes=("", "_market"))

    latest_date = pd.to_datetime(prices.get("observation_date"), errors="coerce").max() if not prices.empty else pd.NaT
    today = pd.Timestamp.now("UTC").date().isoformat()

    r30 = pd.to_numeric(_series(summary, "return_30d"), errors="coerce")
    r90 = pd.to_numeric(_series(summary, "return_90d"), errors="coerce")
    vol = pd.to_numeric(_series(summary, "annualized_volatility"), errors="coerce")
    conf = pd.to_numeric(_series(summary, "projection_confidence"), errors="coerce")
    quality = pd.to_numeric(_series(summary, "price_data_quality"), errors="coerce")
    mi = pd.to_numeric(_series(summary, "market_intelligence_score"), errors="coerce")
    current = pd.to_numeric(
        _series(summary, "current_price").fillna(_series(summary, "latest_price")),
        errors="coerce",
    )
    target = pd.to_numeric(_series(summary, "target_buy_price"), errors="coerce")
    ath = pd.to_numeric(_series(summary, "ath_price"), errors="coerce")
    atl = pd.to_numeric(_series(summary, "atl_price"), errors="coerce")

    signals = _series(summary, "buy_signal", "").fillna("").astype(str)
    ratings = _series(summary, "rating", "").fillna("").astype(str)

    row = {
        "snapshot_date": today,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_products": len(summary),
        "products_with_current_price": int(current.notna().sum()),
        "products_updated_today": _products_updated_today(prices),
        "average_return_30d": round(float(r30.mean()), 4) if r30.notna().any() else None,
        "average_return_90d": round(float(r90.mean()), 4) if r90.notna().any() else None,
        "median_return_30d": round(float(r30.median()), 4) if r30.notna().any() else None,
        "average_volatility": round(float(vol.mean()), 4) if vol.notna().any() else None,
        "buy_signal_count": int(signals.isin(["Buy", "Strong Buy", "Accumulate"]).sum()),
        "watch_signal_count": int(signals.eq("Watch").sum()),
        "wait_signal_count": int(signals.isin(["Wait", "Speculative / Wait"]).sum()),
        "avoid_signal_count": int(ratings.eq("Avoid").sum() + signals.eq("Avoid").sum()),
        "below_target_count": int(((current <= target) & current.notna() & target.notna()).sum()),
        "at_ath_count": int(((current >= ath * 0.99) & current.notna() & ath.notna()).sum()),
        "near_atl_count": int(((current <= atl * 1.05) & current.notna() & atl.notna()).sum()),
        "average_confidence": round(float(conf.mean()), 2) if conf.notna().any() else None,
        "average_data_quality": round(float(quality.mean()), 2) if quality.notna().any() else None,
        "average_market_intelligence": round(float(mi.mean()), 2) if mi.notna().any() else None,
        "market_index_level": None,
        "market_breadth_positive_pct": round(float((r30 > 0).mean() * 100), 2) if r30.notna().any() else None,
        "notes": "Module 2 market health snapshot.",
    }

    out = pd.DataFrame([row])
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO market_health_history (
                snapshot_date, generated_at_utc, total_products,
                products_with_current_price, products_updated_today,
                average_return_30d, average_return_90d, median_return_30d,
                average_volatility, buy_signal_count, watch_signal_count,
                wait_signal_count, avoid_signal_count, below_target_count,
                at_ath_count, near_atl_count, average_confidence,
                average_data_quality, average_market_intelligence,
                market_index_level, market_breadth_positive_pct, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                generated_at_utc=excluded.generated_at_utc,
                total_products=excluded.total_products,
                products_with_current_price=excluded.products_with_current_price,
                products_updated_today=excluded.products_updated_today,
                average_return_30d=excluded.average_return_30d,
                average_return_90d=excluded.average_return_90d,
                median_return_30d=excluded.median_return_30d,
                average_volatility=excluded.average_volatility,
                buy_signal_count=excluded.buy_signal_count,
                watch_signal_count=excluded.watch_signal_count,
                wait_signal_count=excluded.wait_signal_count,
                avoid_signal_count=excluded.avoid_signal_count,
                below_target_count=excluded.below_target_count,
                at_ath_count=excluded.at_ath_count,
                near_atl_count=excluded.near_atl_count,
                average_confidence=excluded.average_confidence,
                average_data_quality=excluded.average_data_quality,
                average_market_intelligence=excluded.average_market_intelligence,
                market_index_level=excluded.market_index_level,
                market_breadth_positive_pct=excluded.market_breadth_positive_pct,
                notes=excluded.notes
            """,
            tuple(_scalar(row[c]) for c in [
                "snapshot_date","generated_at_utc","total_products",
                "products_with_current_price","products_updated_today",
                "average_return_30d","average_return_90d","median_return_30d",
                "average_volatility","buy_signal_count","watch_signal_count",
                "wait_signal_count","avoid_signal_count","below_target_count",
                "at_ath_count","near_atl_count","average_confidence",
                "average_data_quality","average_market_intelligence",
                "market_index_level","market_breadth_positive_pct","notes"
            ]),
        )
        connection.commit()
    finally:
        connection.close()
    return out
