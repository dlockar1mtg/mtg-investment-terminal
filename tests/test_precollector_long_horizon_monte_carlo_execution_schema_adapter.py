from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_precollector_long_horizon_monte_carlo_execution_schema_adapter.py"


def load_module():
    spec = importlib.util.spec_from_file_location("monte_carlo_schema_adapter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_price_date_alias_is_normalized():
    module = load_module()
    frame = pd.DataFrame({
        "tcgplayer_product_id": ["1"],
        "market_price": ["100"],
        "price_date": ["2026-08-01"],
    })
    normalized = module.normalize_authority_frame(frame)
    assert "observed_at" in normalized.columns
    assert "price_date" not in normalized.columns


def test_foundation_frame_is_not_modified():
    module = load_module()
    frame = pd.DataFrame({
        "tcgplayer_product_id": ["1"],
        "current_price": ["100"],
        "forecast_route": ["DIRECT_HISTORY_CALIBRATED"],
        "snapshot_date": ["2026-08-01"],
    })
    normalized = module.normalize_authority_frame(frame)
    assert list(normalized.columns) == list(frame.columns)


def test_parseable_date_like_column_is_resolved():
    module = load_module()
    frame = pd.DataFrame({
        "tcgplayer_product_id": ["1", "2"],
        "market_price": ["100", "110"],
        "canonical_snapshot_time": ["2026-07-01", "2026-08-01"],
    })
    normalized = module.normalize_authority_frame(frame)
    assert "observed_at" in normalized.columns


def test_unresolved_history_schema_fails_closed_with_columns():
    module = load_module()
    frame = pd.DataFrame({
        "tcgplayer_product_id": ["1"],
        "market_price": ["100"],
        "sequence": ["1"],
    })
    with pytest.raises(RuntimeError, match="CANONICAL_HISTORY_DATE_COLUMN_UNRESOLVED"):
        module.normalize_authority_frame(frame)


def test_adapter_main_is_callable():
    assert callable(load_module().main)
