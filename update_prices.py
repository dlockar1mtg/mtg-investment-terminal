from __future__ import annotations

from pathlib import Path
import pandas as pd

from config import (
    PRODUCT_MAP_FILE,
    SOURCE_CACHE_DIR,
    DATABASE_FILE,
    USE_TCGCSV,
    USE_TCGPLAYER_API,
    USE_MTGJSON,
    USE_SCRYFALL,
    RAW_DATA_DIR,
    DISCOVER_ALL_COLLECTOR_BOXES,
    DISCOVERED_PRODUCTS_FILE,
    DISCOVERED_MODEL_INPUT_FILE,
    TCGCSV_MAGIC_CATEGORY_ID,
    USE_PRODUCT_MASTER,
    PRODUCT_MASTER_MODEL_INPUT_FILE,
)
from database.db import (
    init_db,
    now_utc,
    upsert_product_mapping,
    insert_price_snapshots,
    log_source_run,
)
from collectors.tcgcsv_collector import collect_tcgcsv_prices
from collectors.tcgplayer_api_collector import collect_tcgplayer_api_prices
from collectors.mtgjson_collector import save_mtgjson_metadata
from collectors.scryfall_collector import collect_scryfall_chase_summary
from collectors.tcgcsv_discovery import discover_collector_booster_boxes
from models.product_master import apply_product_master, approved_rows_to_latest_cache
from models.investment_features import build_investment_features
from models.market_database import apply_rolling_metrics
from models.real_signal_engine import apply_real_signal_engine
from models.market_intelligence import apply_market_intelligence


def require_rows(df, stage_name):
    if df is None or df.empty:
        raise RuntimeError(f"{stage_name} produced zero rows.")
    print(f"Stage OK: {stage_name} rows={len(df)}")
    return df


def load_product_map():
    if not Path(PRODUCT_MAP_FILE).exists():
        return pd.DataFrame()
    return pd.read_csv(PRODUCT_MAP_FILE)


def write_model_input_from_product_master(discovered_df):
    require_rows(discovered_df, "TCGCSV discovery")

    Path(DISCOVERED_PRODUCTS_FILE).parent.mkdir(parents=True, exist_ok=True)
    discovered_df.to_csv(DISCOVERED_PRODUCTS_FILE, index=False)

    if USE_PRODUCT_MASTER:
        model_df, master_df, candidates_df = apply_product_master(discovered_df)
        print(f"Raw collector booster products discovered: {len(discovered_df)}")
        print(f"Product master rows: {len(master_df)}")
        print(f"Candidate rows: {len(candidates_df)}")
        require_rows(model_df, "Approved product master selection")

        model_df = build_investment_features(model_df)
        require_rows(model_df, "Investment feature build")

        model_df = apply_rolling_metrics(model_df)
        require_rows(model_df, "Rolling market database metrics")

        model_df = apply_real_signal_engine(model_df)
        require_rows(model_df, "Real signal engine")

        model_df = apply_market_intelligence(model_df)
        require_rows(model_df, "Market intelligence + Monte Carlo")

        model_df.to_csv(PRODUCT_MASTER_MODEL_INPUT_FILE, index=False)
        model_df.to_csv(DISCOVERED_MODEL_INPUT_FILE, index=False)

        print(f"Approved investment products selected for scoring: {len(model_df)}")
        print("Review candidates at: data/product_master/product_selection_review.csv")
        print("Daily price observations at: data/market_database/daily_price_observations.csv")
        print("Rolling metrics at: data/rolling_metrics/rolling_price_metrics.csv")
        print("Real signals at: data/market_signals/real_signal_scores.csv")
        return PRODUCT_MASTER_MODEL_INPUT_FILE, model_df

    discovered_df.to_csv(DISCOVERED_MODEL_INPUT_FILE, index=False)
    return DISCOVERED_MODEL_INPUT_FILE, discovered_df


def write_latest_cache_from_model(model_df):
    Path(SOURCE_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    latest_file = Path(SOURCE_CACHE_DIR) / "latest_prices.csv"

    if model_df is None or model_df.empty:
        return False

    latest = approved_rows_to_latest_cache(model_df)
    latest.to_csv(latest_file, index=False)
    print(f"Updated product-master source cache: {latest_file}")
    return True


def rows_to_price_snapshots(model_df):
    if model_df is None or model_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in model_df.iterrows():
        rows.append({
            "box_name": r.get("box_name"),
            "tcgplayer_product_id": r.get("approved_tcgplayer_product_id") or r.get("tcgplayer_product_id"),
            "source_name": r.get("price_source") or "product_master_tcgcsv",
            "market_price": r.get("current_price"),
            "low_price": r.get("estimated_floor_price") or r.get("low_price"),
            "mid_price": r.get("mid_price"),
            "high_price": r.get("high_price"),
            "direct_low_price": r.get("direct_low_price"),
            "sub_type_name": r.get("sub_type_name"),
            "source_timestamp": r.get("last_price_checked"),
            "collected_at": r.get("last_price_checked") or now_utc(),
            "price_data_quality": r.get("price_data_quality", 95),
            "raw_payload": "{}",
        })
    return pd.DataFrame(rows)


def update_all_prices():
    init_db(DATABASE_FILE)

    model_df = pd.DataFrame()

    if DISCOVER_ALL_COLLECTOR_BOXES and USE_TCGCSV:
        started = now_utc()
        try:
            discovered_df, _raw_price_df = discover_collector_booster_boxes(TCGCSV_MAGIC_CATEGORY_ID)
            _input_file, model_df = write_model_input_from_product_master(discovered_df)

            price_rows = rows_to_price_snapshots(model_df)
            rows = insert_price_snapshots(price_rows, DATABASE_FILE)
            write_latest_cache_from_model(model_df)

            log_source_run("tcgcsv_product_master_v12_1", "success", started, now_utc(), len(model_df), f"price rows={rows}")
        except Exception as exc:
            log_source_run("tcgcsv_product_master_v12_1", "failed", started, now_utc(), 0, str(exc))
            print(f"TCGCSV product-master update failed: {exc}")
            raise

    product_map = load_product_map()
    if not product_map.empty:
        upsert_product_mapping(product_map, DATABASE_FILE)

    if USE_TCGPLAYER_API:
        started = now_utc()
        try:
            df = collect_tcgplayer_api_prices(PRODUCT_MAP_FILE)
            rows = insert_price_snapshots(df, DATABASE_FILE)
            log_source_run("tcgplayer_api", "success", started, now_utc(), rows, "")
        except Exception as exc:
            log_source_run("tcgplayer_api", "failed", started, now_utc(), 0, str(exc))
            print(f"TCGplayer API update failed: {exc}")

    if USE_TCGCSV and not DISCOVER_ALL_COLLECTOR_BOXES:
        started = now_utc()
        try:
            df = collect_tcgcsv_prices(PRODUCT_MAP_FILE)
            rows = insert_price_snapshots(df, DATABASE_FILE)
            log_source_run("tcgcsv", "success", started, now_utc(), rows, "")
        except Exception as exc:
            log_source_run("tcgcsv", "failed", started, now_utc(), 0, str(exc))
            print(f"TCGCSV update failed: {exc}")

    if USE_MTGJSON:
        started = now_utc()
        try:
            meta = save_mtgjson_metadata(Path(RAW_DATA_DIR) / "mtgjson")
            log_source_run("mtgjson", "success", started, now_utc(), len(meta), "metadata only")
        except Exception as exc:
            log_source_run("mtgjson", "failed", started, now_utc(), 0, str(exc))
            print(f"MTGJSON update failed: {exc}")

    if USE_SCRYFALL:
        started = now_utc()
        try:
            chase = collect_scryfall_chase_summary(PRODUCT_MAP_FILE)
            log_source_run("scryfall", "success", started, now_utc(), len(chase), "chase-card summary only")
        except Exception as exc:
            log_source_run("scryfall", "failed", started, now_utc(), 0, str(exc))
            print(f"Scryfall update failed: {exc}")

    return model_df


if __name__ == "__main__":
    update_all_prices()
