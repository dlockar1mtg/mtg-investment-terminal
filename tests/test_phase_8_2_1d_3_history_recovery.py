from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "recover_phase_8_2_1d_3_secret_lair_history.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "phase_8_2_1d_3_recovery",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_id_removes_secret_lair_prefix() -> None:
    module = load_module()
    assert (
        module.normalize_id("MTG:SECRET_LAIR:SL-123")
        == "SL-123"
    )
    assert module.normalize_id("SL-123") == "SL-123"


def test_alias_detection_supports_archive_fields() -> None:
    module = load_module()
    row = {
        "product_id": "SL-1",
        "snapshot_date": "2025-01-31",
        "tcg_market_price": "125.50",
        "provider": "tcgcsv",
    }
    assert (
        module.first_present(row, module.ID_ALIASES)
        == "SL-1"
    )
    assert (
        module.first_present(row, module.DATE_ALIASES)
        == "2025-01-31"
    )
    assert (
        module.first_present(row, module.MARKET_PRICE_ALIASES)
        == "125.50"
    )


def test_deduplicate_uses_daily_source_median() -> None:
    module = load_module()
    rows = [
        {
            "observation_date": "2025-01-31",
            "secret_lair_id": "SL-1",
            "source_name": "tcgcsv",
            "market_price": 100.0,
            "low_price": 90.0,
            "source_record_id": "a",
            "source_file": "a.csv",
        },
        {
            "observation_date": "2025-01-31",
            "secret_lair_id": "SL-1",
            "source_name": "TCGCSV",
            "market_price": 120.0,
            "low_price": 95.0,
            "source_record_id": "b",
            "source_file": "b.csv",
        },
    ]
    output = module.deduplicate(rows)
    assert len(output) == 1
    assert output[0]["market_price"] == 110.0
    assert output[0]["low_price"] == 92.5


def test_parse_month_as_first_day() -> None:
    module = load_module()
    assert (
        module.parse_date("2025-03").isoformat()
        == "2025-03-01"
    )
