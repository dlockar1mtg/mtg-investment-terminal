from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_phase_8_2_1c_secret_lair_intelligence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("phase_8_2_1c_audit", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_field_semantics_separate_history_from_forecast() -> None:
    module = load_module()
    assert module.classify_field("realized_cagr_pct") == "HISTORICAL_PERFORMANCE"
    assert module.classify_field("five_year_base_usd") == "FORWARD_FORECAST"
    assert module.classify_field("current_market_value_usd") == "CURRENT_OR_RANGE_VALUATION"
    assert module.classify_field("liquidity_confidence") == "QUALITY_OR_LIQUIDITY"


def test_secret_lair_detection() -> None:
    module = load_module()
    assert module.is_secret_lair({"lane": "SECRET_LAIR"})
    assert module.is_secret_lair({"asset_id": "MTG:SECRET_LAIR:123"})
    assert not module.is_secret_lair({"lane": "COLLECTOR_BOOSTER_BOX"})
