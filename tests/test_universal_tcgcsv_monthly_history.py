from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "backfill_universal_tcgcsv_monthly_history.py"
    spec = importlib.util.spec_from_file_location(
        "backfill_universal_tcgcsv_monthly_history",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_eligible_products_fail_closed():
    module = load_module()
    rows = [
        {
            "universal_mtg_product_id": "A",
            "tcgcsv_archive_eligible": "true",
            "tcgplayer_product_id": "1",
            "tcgcsv_category_id": "1",
            "tcgcsv_group_id": "2",
        },
        {
            "universal_mtg_product_id": "B",
            "tcgcsv_archive_eligible": "false",
            "tcgplayer_product_id": "2",
            "tcgcsv_category_id": "1",
            "tcgcsv_group_id": "3",
        },
    ]
    assert [row["universal_mtg_product_id"]
            for row in module.eligible_products(rows)] == ["A"]


def test_group_products_supports_many_groups():
    module = load_module()
    grouped = module.group_products([
        {
            "tcgcsv_category_id": "1",
            "tcgcsv_group_id": "2",
        },
        {
            "tcgcsv_category_id": "1",
            "tcgcsv_group_id": "3",
        },
    ])
    assert set(grouped) == {("1", "2"), ("1", "3")}


def test_merge_by_key_is_append_safe_and_last_write_wins():
    module = load_module()
    merged = module.merge_by_key(
        [{"id": "A", "date": "2024-01-01", "value": "old"}],
        [
            {"id": "A", "date": "2024-01-01", "value": "new"},
            {"id": "B", "date": "2024-01-01", "value": "x"},
        ],
        ("id", "date"),
    )
    assert len(merged) == 2
    assert next(row for row in merged if row["id"] == "A")["value"] == "new"


def test_select_price_prefers_normal_subtype():
    module = load_module()
    selected = module.select_price([
        {"subTypeName": "Foil", "marketPrice": 10},
        {"subTypeName": "Normal", "marketPrice": 20},
    ])
    assert selected["marketPrice"] == 20
