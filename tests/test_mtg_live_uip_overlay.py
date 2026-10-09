from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "apply_mtg_live_uip_overlay.py"
    spec = importlib.util.spec_from_file_location("apply_mtg_live_uip_overlay", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_identifier_index_supports_source_ids():
    module = load_module()
    rows = [{"canonical_product_id": "ABC", "price": "42"}]
    assert module.index_rows(rows)["ABC"]["price"] == "42"


def test_price_field_selection():
    module = load_module()
    assert module.first({"median_price_usd": "100"}, module.PRICE_FIELDS) == "100"
    assert module.first({"consolidated_price": "222.56"}, module.PRICE_FIELDS) == "222.56"
    assert module.first({"consolidated_market_price": "470.95"}, module.PRICE_FIELDS) == "470.95"


def test_only_buy_type_calls_are_recommendation_eligible():
    module = load_module()
    assert [module.recommendation_eligible(s) for s in ("STRONG_BUY", "BUY", "buy", "ACCUMULATE")] == ["YES"] * 4
    assert [module.recommendation_eligible(s) for s in ("HOLD", "AVOID", "WATCH", "NO_ACTION", "", None)] == ["NO"] * 6
