from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from terminal2.config import ROOT_DIR
from terminal2.db.module2_migration import migrate_module2
from terminal2.db.schema import get_connection


DATA_DIR = Path(ROOT_DIR) / "data"
DASHBOARD_DIR = DATA_DIR / "dashboard"
MARKET_DIR = DASHBOARD_DIR / "market"
ALERTS_DIR = DASHBOARD_DIR / "alerts"
EXECUTIVE_DIR = DASHBOARD_DIR / "executive"
ANALYTICS_CURRENT_DIR = DATA_DIR / "analytics" / "current"


def _read(sql):
    connection = get_connection()
    try:
        return pd.read_sql_query(sql, connection)
    finally:
        connection.close()


def _write(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return len(df)


def _market_signals(intelligence):
    if intelligence.empty:
        return intelligence

    df = intelligence.copy()
    score = pd.to_numeric(df["market_intelligence_score"], errors="coerce")
    confidence = pd.to_numeric(df["market_intelligence_confidence"], errors="coerce")
    supply = pd.to_numeric(df["supply_signal_score"], errors="coerce")
    sales = pd.to_numeric(df["sales_velocity_score"], errors="coerce")
    relative = pd.to_numeric(df["market_relative_strength"], errors="coerce")

    df["market_signal"] = np.select(
        [
            (score >= 75) & (confidence >= 60),
            (score >= 65) & (confidence >= 40),
            score >= 55,
            score < 40,
        ],
        ["Strong", "Positive", "Neutral / Watch", "Weak"],
        default="Neutral",
    )
    df["signal_reason"] = np.select(
        [
            (supply >= 70) & (sales >= 70),
            relative >= 70,
            supply >= 70,
            sales >= 70,
            relative <= 35,
        ],
        [
            "Supply contraction and sales velocity are both strong.",
            "Product is outperforming the sealed market.",
            "Supply conditions are favorable.",
            "Sales velocity is favorable.",
            "Product is underperforming the sealed market.",
        ],
        default="No dominant market signal.",
    )
    return df


def _market_alerts(signals):
    if signals.empty:
        return pd.DataFrame(columns=[
            "investment_product_id", "box_name", "alert_type", "severity",
            "alert_message", "generated_at_utc"
        ])

    rows = []
    generated = datetime.now(timezone.utc).isoformat()
    for _, row in signals.iterrows():
        score = row.get("market_intelligence_score")
        confidence = row.get("market_intelligence_confidence")
        alpha30 = row.get("market_alpha_30d")
        supply = row.get("supply_signal_score")
        supply_conf = row.get("supply_confidence")
        sales = row.get("sales_velocity_score")
        sales_conf = row.get("sales_confidence")

        if pd.notna(score) and score >= 72 and pd.notna(confidence) and confidence >= 50:
            rows.append({
                "investment_product_id": row.get("investment_product_id"),
                "box_name": row.get("box_name"),
                "alert_type": "MARKET_STRENGTH",
                "severity": "High",
                "alert_message": f"Market intelligence score is {score:.1f} with {confidence:.1f}% confidence.",
                "generated_at_utc": generated,
            })
        if pd.notna(alpha30) and alpha30 >= 0.10:
            rows.append({
                "investment_product_id": row.get("investment_product_id"),
                "box_name": row.get("box_name"),
                "alert_type": "MARKET_OUTPERFORMANCE",
                "severity": "Medium",
                "alert_message": f"30-day alpha versus the sealed market is {alpha30 * 100:.1f}%.",
                "generated_at_utc": generated,
            })
        if pd.notna(supply) and supply >= 75 and pd.notna(supply_conf) and supply_conf >= 50:
            rows.append({
                "investment_product_id": row.get("investment_product_id"),
                "box_name": row.get("box_name"),
                "alert_type": "SUPPLY_CONTRACTION",
                "severity": "Medium",
                "alert_message": f"Supply signal is {supply:.1f}.",
                "generated_at_utc": generated,
            })
        if pd.notna(sales) and sales >= 75 and pd.notna(sales_conf) and sales_conf >= 50:
            rows.append({
                "investment_product_id": row.get("investment_product_id"),
                "box_name": row.get("box_name"),
                "alert_type": "SALES_VELOCITY",
                "severity": "Medium",
                "alert_message": f"Sales velocity signal is {sales:.1f}.",
                "generated_at_utc": generated,
            })

    return pd.DataFrame(rows)


def _update_manifest(entries):
    manifest_path = DASHBOARD_DIR / "dataset_manifest.csv"
    generated = datetime.now(timezone.utc).isoformat()

    existing = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame(
        columns=["dataset", "path", "rows", "generated_at_utc"]
    )
    new = pd.DataFrame([
        {
            "dataset": dataset,
            "path": str(path.relative_to(DATA_DIR)),
            "rows": rows,
            "generated_at_utc": generated,
        }
        for dataset, path, rows in entries
    ])

    if not existing.empty:
        existing = existing[~existing["dataset"].isin(new["dataset"])]
    combined = pd.concat([existing, new], ignore_index=True, sort=False)
    combined.to_csv(manifest_path, index=False)
    (DATA_DIR / "analytics" / "dataset_manifest.csv").parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(DATA_DIR / "analytics" / "dataset_manifest.csv", index=False)

    dictionary_path = DASHBOARD_DIR / "data_dictionary.csv"
    dictionary = pd.read_csv(dictionary_path) if dictionary_path.exists() else pd.DataFrame(
        columns=["dataset", "path", "column_name", "inferred_dtype"]
    )
    dictionary = dictionary[~dictionary["dataset"].isin(new["dataset"])] if not dictionary.empty else dictionary
    rows = []
    for dataset, path, _ in entries:
        try:
            sample = pd.read_csv(path, nrows=10)
            for col in sample.columns:
                rows.append({
                    "dataset": dataset,
                    "path": str(path.relative_to(DATA_DIR)),
                    "column_name": col,
                    "inferred_dtype": str(sample[col].dtype),
                })
        except Exception:
            pass
    dictionary = pd.concat([dictionary, pd.DataFrame(rows)], ignore_index=True, sort=False)
    dictionary.to_csv(dictionary_path, index=False)


def export_module2_dashboard():
    migrate_module2()
    intelligence = _read("""
        SELECT mi.*, p.box_name, p.set_name, p.product_type, p.asset_class
        FROM market_intelligence mi
        LEFT JOIN products p USING(investment_product_id)
        ORDER BY mi.market_intelligence_score DESC
    """)
    supply = _read("""
        SELECT so.*, p.box_name, p.product_type, p.asset_class
        FROM supply_observations so
        LEFT JOIN products p USING(investment_product_id)
        ORDER BY so.observation_date, so.investment_product_id
    """)
    sales = _read("""
        SELECT sa.*, p.box_name, p.product_type, p.asset_class
        FROM sales_observations sa
        LEFT JOIN products p USING(investment_product_id)
        ORDER BY sa.observation_date, sa.investment_product_id
    """)
    market_health = _read("SELECT * FROM market_health_history ORDER BY snapshot_date")
    source_health = _read("SELECT * FROM source_health_history ORDER BY snapshot_date, source_name")
    signals = _market_signals(intelligence)
    alerts = _market_alerts(signals)

    entries = []

    for dataset, df, path in [
        ("market_intelligence", intelligence, MARKET_DIR / "market_intelligence.csv"),
        ("market_signals", signals, MARKET_DIR / "market_signals.csv"),
        ("market_health", market_health, MARKET_DIR / "market_health.csv"),
        ("source_health", source_health, MARKET_DIR / "source_health.csv"),
        ("supply_metrics", supply, MARKET_DIR / "supply_metrics.csv"),
        ("liquidity", sales, MARKET_DIR / "liquidity.csv"),
        ("market_alerts", alerts, ALERTS_DIR / "market_intelligence_alerts.csv"),
        ("current_market_intelligence", intelligence, ANALYTICS_CURRENT_DIR / "market_intelligence.csv"),
        ("current_market_health", market_health.tail(1), ANALYTICS_CURRENT_DIR / "market_health.csv"),
    ]:
        rows = _write(df, path)
        entries.append((dataset, path, rows))

    # Executive market health is a stable one-row table.
    executive_path = EXECUTIVE_DIR / "market_health_summary.csv"
    rows = _write(market_health.tail(1), executive_path)
    entries.append(("market_health_summary", executive_path, rows))

    _update_manifest(entries)

    return {
        "datasets": len(entries),
        "market_intelligence_rows": len(intelligence),
        "supply_rows": len(supply),
        "sales_rows": len(sales),
        "market_alert_rows": len(alerts),
        "market_health_rows": len(market_health),
        "source_health_rows": len(source_health),
    }
