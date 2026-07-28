from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load(name: str, filename: str):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_current_coverage_reconciles_missing_rows():
    module = load("coverage", "audit_tcgcsv_current_price_coverage.py")
    maps = [
        {"investment_product_id": "A", "box_name": "A", "source_product_name": "A", "tcgplayer_product_id": "1", "tcgcsv_category_id": "1", "tcgcsv_group_id": "2576"},
        {"investment_product_id": "B", "box_name": "B", "source_product_name": "B", "tcgplayer_product_id": "2", "tcgcsv_category_id": "1", "tcgcsv_group_id": "2576"},
    ]
    observations = [{"investment_product_id": "A"}]
    missing, summary = module.build(maps, observations)
    assert len(missing) == 1
    assert missing[0]["investment_product_id"] == "B"
    assert summary["products_without_current_price"] == 1


def test_archive_month_starts_respects_first_exact_date():
    module = load("archive", "backfill_confirmed_tcgcsv_monthly_history.py")
    dates = module.month_starts("2024-02-08", "2024-04-01")
    assert dates == ["2024-02-08", "2024-03-01", "2024-04-01"]


def test_archive_select_price_prefers_normal():
    module = load("archive2", "backfill_confirmed_tcgcsv_monthly_history.py")
    selected = module.select_price([
        {"subTypeName": "Foil", "marketPrice": 1},
        {"subTypeName": "Normal", "marketPrice": 2},
    ])
    assert selected["marketPrice"] == 2
