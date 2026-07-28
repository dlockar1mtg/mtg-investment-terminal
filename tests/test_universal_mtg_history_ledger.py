from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_universal_mtg_history_ledger.py"
    spec = importlib.util.spec_from_file_location(
        "build_universal_mtg_history_ledger",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_archive_normalization_preserves_governed_identity():
    module = load_module()
    rows = module.normalize_archive([{
        "universal_mtg_product_id": "UMTG-1",
        "canonical_product_name": "Example",
        "product_class": "SECRET_LAIR",
        "tcgplayer_product_id": "123",
        "tcgcsv_category_id": "1",
        "tcgcsv_group_id": "2576",
        "observation_date": "2026-07-01",
        "selected_price": "100",
        "run_id": "run",
    }])
    assert rows[0]["canonical_product_id"] == "UMTG-1"
    assert rows[0]["source_name"] == "TCGCSV_ARCHIVE"
    assert rows[0]["market_price"] == "100"


def test_dedupe_raw_uses_observation_fingerprint():
    module = load_module()
    rows = module.dedupe_raw([
        {
            "canonical_product_id": "A",
            "source_name": "EBAY",
            "observation_date": "2026-01-01",
            "market_price": "10",
            "observation_fingerprint": "same",
        },
        {
            "canonical_product_id": "A",
            "source_name": "EBAY",
            "observation_date": "2026-01-01",
            "market_price": "11",
            "observation_fingerprint": "same",
        },
    ])
    assert len(rows) == 1
    assert rows[0]["market_price"] == "11"


def test_history_status_contract():
    module = load_module()
    assert module.history_status(30) == "HISTORY_30_PLUS_DATES"
    assert module.history_status(2) == "HISTORY_2_TO_29_DATES"
    assert module.history_status(1) == "HISTORY_1_DATE"
    assert module.history_status(0) == "NO_DIRECT_HISTORY"


def test_no_history_ebay_route_is_explicit():
    module = load_module()
    routing = [{
        "universal_mtg_product_id": "A",
        "canonical_product_name": "A",
        "product_class": "SECRET_LAIR",
        "tcgplayer_product_id": "",
        "tcgcsv_identity_status": "TCGCSV_ID_NOT_FOUND",
        "tcgcsv_archive_eligible": "false",
        "ebay_history_eligible": "true",
        "primary_history_route": "EBAY_DAILY_ACCUMULATION",
    }]
    result = module.build_verification(routing, [])
    assert result[0]["history_completion_route"] == (
        "EBAY_ACCUMULATION_REQUIRED"
    )
