from __future__ import annotations
from pathlib import Path
import pandas as pd
from terminal2.config import DB_FILE, PRODUCT_MASTER_FILE
from terminal2.db.schema import get_connection, init_db
from terminal2.db.module1_migration import migrate_module1


def infer_era(year):
    try: year = int(float(year))
    except Exception: return None
    if year <= 2002: return "Early Magic"
    if year <= 2018: return "Modern Expansion"
    if year <= 2023: return "Premium Era"
    return "Current Era"


def sync_product_master(product_master_file: Path = PRODUCT_MASTER_FILE):
    init_db(); migrate_module1()
    if not Path(product_master_file).exists():
        raise FileNotFoundError(f"Product master not found: {product_master_file}")
    df = pd.read_csv(product_master_file, dtype=str)
    approved = df[df["approval_status"].astype(str).str.lower() == "approved"].copy()
    connection = get_connection()
    try:
        for _, row in approved.iterrows():
            product_type = row.get("investment_product_type", "Collector Booster Display")
            release_date = row.get("release_date")
            release_year = None
            if release_date:
                try: release_year = pd.to_datetime(release_date).year
                except Exception: pass
            text = f"{row.get('set_name','')} {row.get('box_name','')}".lower()
            ub_terms = ["universes beyond", "lord of the rings", "final fantasy", "fallout", "doctor who", "marvel", "assassin", "warhammer", "avatar", "hobbit", "teenage mutant"]
            connection.execute("""INSERT INTO products (investment_product_id,set_name,box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id,product_type,asset_class,approval_status,approval_method,release_date,release_year,era,franchise,universes_beyond,masters_product,secret_lair,foil_variant,language,notes,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(investment_product_id) DO UPDATE SET set_name=excluded.set_name,box_name=excluded.box_name,tcgplayer_product_id=excluded.tcgplayer_product_id,tcgcsv_category_id=excluded.tcgcsv_category_id,tcgcsv_group_id=excluded.tcgcsv_group_id,product_type=excluded.product_type,asset_class=excluded.asset_class,approval_status=excluded.approval_status,approval_method=excluded.approval_method,release_date=COALESCE(excluded.release_date,products.release_date),release_year=COALESCE(excluded.release_year,products.release_year),era=COALESCE(excluded.era,products.era),franchise=COALESCE(excluded.franchise,products.franchise),universes_beyond=excluded.universes_beyond,masters_product=excluded.masters_product,secret_lair=excluded.secret_lair,foil_variant=COALESCE(excluded.foil_variant,products.foil_variant),language=COALESCE(excluded.language,products.language),notes=excluded.notes,updated_at=CURRENT_TIMESTAMP""", (
                row.get("investment_product_id"), row.get("set_name"), row.get("box_name"), row.get("approved_tcgplayer_product_id"), row.get("tcgcsv_category_id"), row.get("tcgcsv_group_id"), product_type, product_type, row.get("approval_status"), row.get("approval_method"), release_date, release_year, infer_era(release_year), row.get("franchise"), int(any(term in text for term in ub_terms)), int("masters" in text), int(product_type == "Secret Lair Drop"), row.get("foil_variant"), row.get("language", "English"), row.get("notes")
            ))
        connection.commit()
    finally:
        connection.close()
    return len(approved)


def load_products_df():
    init_db(); migrate_module1(); connection = get_connection()
    try: return pd.read_sql_query("SELECT * FROM products ORDER BY product_type, set_name", connection)
    finally: connection.close()


def insert_price_observations(
    rows,
    source_run_id=None,
    db_file=None,
):
    if not rows:
        return 0

    database_path = DB_FILE if db_file is None else Path(db_file)
    init_db(database_path)
    connection = get_connection(database_path)
    count = 0
    try:
        for row in rows:
            connection.execute("""INSERT INTO price_observations (observation_date,investment_product_id,tcgplayer_product_id,price_source,market_price,low_price,mid_price,high_price,price_data_quality,source_run_id,raw_payload) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(observation_date,investment_product_id,price_source) DO UPDATE SET tcgplayer_product_id=excluded.tcgplayer_product_id,market_price=excluded.market_price,low_price=excluded.low_price,mid_price=excluded.mid_price,high_price=excluded.high_price,price_data_quality=excluded.price_data_quality,source_run_id=excluded.source_run_id,raw_payload=excluded.raw_payload,created_at=CURRENT_TIMESTAMP""", (row.get("observation_date"), row.get("investment_product_id"), row.get("tcgplayer_product_id"), row.get("price_source", "unknown"), row.get("market_price"), row.get("low_price"), row.get("mid_price"), row.get("high_price"), row.get("price_data_quality", 80), source_run_id, row.get("raw_payload", "{}")))
            count += 1
        connection.commit()
    finally: connection.close()
    return count


def load_price_observations_df():
    init_db(); connection = get_connection()
    try: return pd.read_sql_query("""SELECT po.*,p.box_name,p.set_name,p.product_type FROM price_observations po LEFT JOIN products p ON p.investment_product_id=po.investment_product_id ORDER BY po.investment_product_id,po.observation_date""", connection)
    finally: connection.close()
