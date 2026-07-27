from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_mtg_daily_history.py"
    spec = importlib.util.spec_from_file_location("build_universal_mtg_daily_history", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def test_listing_rows_collapse_to_one_source_day():
    module = load_module()
    rows = [
        {"canonical_product_id":"A","canonical_product_name":"A","product_class":"SECRET_LAIR","source_name":"EBAY","observation_date":"2026-07-23T10:00:00Z","market_price":"100","price_field":"market_price","source_file":"a.csv","is_live_observation":"false"},
        {"canonical_product_id":"A","canonical_product_name":"A","product_class":"SECRET_LAIR","source_name":"EBAY","observation_date":"2026-07-23T11:00:00Z","market_price":"120","price_field":"market_price","source_file":"b.csv","is_live_observation":"false"},
    ]
    daily = module.build_daily_source(rows)
    assert len(daily) == 1
    assert daily[0]["daily_market_price"] == 110.0
    assert daily[0]["raw_observation_count"] == 2

def test_model_valuations_are_not_direct_history():
    module = load_module()
    rows = [{"canonical_product_id":"A","source_name":"MODEL","observation_date":"2026-07-23","market_price":"100","price_field":"evaluated_market_value_usd"}]
    assert module.build_daily_source(rows) == []

def test_verification_uses_distinct_dates_and_is_not_source_exhaustion():
    module = load_module()
    coverage = [{"canonical_product_id":"A","canonical_product_name":"A","product_class":"SECRET_LAIR","tcgplayer_product_id":"","has_ebay_identity":"true"}]
    daily = [
        {"canonical_product_id":"A","canonical_product_name":"A","product_class":"SECRET_LAIR","observation_date":"2026-07-01","source_names":"EBAY"},
        {"canonical_product_id":"A","canonical_product_name":"A","product_class":"SECRET_LAIR","observation_date":"2026-07-02","source_names":"EBAY"},
    ]
    result = module.build_verification(coverage, daily)
    assert result[0]["distinct_history_dates"] == 2
    assert result[0]["history_verification_status"] == "HISTORY_2_TO_29_DATES"
    assert result[0]["fresh_tcgcsv_archive_search_status"] == "NOT_YET_EXECUTED"
    assert result[0]["source_exhaustion_status"] == "NOT_CERTIFIED"
