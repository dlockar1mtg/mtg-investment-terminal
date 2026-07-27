from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "select_mtg_marketplace_batch.py"
    spec = importlib.util.spec_from_file_location(
        "select_mtg_marketplace_batch", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_rows(count: int = 60):
    rows = []
    for index in range(count):
        tcg = index < 10
        rows.append({
            "canonical_product_id": f"P-{index:03d}",
            "product_class": (
                "COLLECTOR_BOOSTER_BOX"
                if tcg else "SECRET_LAIR"
            ),
            "tcgplayer_product_id": str(index) if tcg else "",
            "collection_lane": (
                "EBAY_AND_TCGCSV" if tcg else "EBAY_ONLY"
            ),
            "mapping_status": "READY",
        })
    return rows


def test_rotating_batch_is_deterministic():
    module = load_module()
    rows = build_rows()
    first_rows, first = module.choose_batch(
        rows,
        batch_size=25,
        run_number=1,
    )
    again_rows, again = module.choose_batch(
        rows,
        batch_size=25,
        run_number=1,
    )
    assert first == again
    assert first_rows == again_rows
    assert first["batch_index"] == 0
    assert first["batch_count"] == 3


def test_next_run_advances_batch():
    module = load_module()
    rows = build_rows()
    _, first = module.choose_batch(
        rows,
        batch_size=25,
        run_number=1,
    )
    _, second = module.choose_batch(
        rows,
        batch_size=25,
        run_number=2,
    )
    assert first["batch_index"] == 0
    assert second["batch_index"] == 1
    assert (
        set(first["ebay_batch_product_ids"])
        .isdisjoint(second["ebay_batch_product_ids"])
    )


def test_all_tcgcsv_products_remain_in_runtime_map():
    module = load_module()
    rows = build_rows()
    runtime_rows, summary = module.choose_batch(
        rows,
        batch_size=25,
        run_number=2,
    )
    tcg_ids = {
        row["tcgplayer_product_id"]
        for row in runtime_rows
        if row["tcgplayer_product_id"]
    }
    assert tcg_ids == {str(index) for index in range(10)}
    assert summary["tcgcsv_full_refresh_products"] == 10


def test_explicit_batch_index_is_supported():
    module = load_module()
    rows = build_rows()
    _, summary = module.choose_batch(
        rows,
        batch_size=25,
        run_number=99,
        requested_batch_index=2,
    )
    assert summary["selection_mode"] == "EXPLICIT_BATCH_INDEX"
    assert summary["batch_index"] == 2
    assert summary["ebay_batch_products"] == 10
