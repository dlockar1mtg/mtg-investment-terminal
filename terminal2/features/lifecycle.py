from __future__ import annotations
import pandas as pd
from terminal2.db.schema import get_connection, init_db


def lifecycle_report():
    init_db()
    connection = get_connection()
    try:
        df = pd.read_sql_query("""SELECT p.investment_product_id,p.box_name,p.product_type,p.release_date,f.observation_count,f.first_observation_date,f.latest_observation_date,f.latest_price,f.ath_price,f.atl_price,f.drawdown_from_ath,f.return_365d FROM products p LEFT JOIN product_features f USING(investment_product_id)""", connection)
    finally:
        connection.close()
    today = pd.Timestamp.now("UTC").tz_localize(None)
    release = pd.to_datetime(df["release_date"], errors="coerce")
    first = pd.to_datetime(df["first_observation_date"], errors="coerce")
    basis = release.fillna(first)
    df["months_since_release"] = ((today.year - basis.dt.year) * 12 + (today.month - basis.dt.month)).astype("Int64")
    def stage(months):
        if pd.isna(months): return "Unknown"
        if months < 0: return "Pre-release"
        if months <= 3: return "Release / Early Supply"
        if months <= 9: return "Supply Peak / Price Discovery"
        if months <= 18: return "Stabilization"
        if months <= 36: return "Supply Contraction / Growth"
        if months <= 60: return "Scarcity"
        return "Legacy"
    df["lifecycle_stage"] = df["months_since_release"].apply(stage)
    return df
