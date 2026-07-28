from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "normalize_universal_mtg_ebay_history_queries.py"
    spec = importlib.util.spec_from_file_location(
        "normalize_universal_mtg_ebay_history_queries",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_standard_suffix_is_removed():
    module = load_module()
    name, actions = module.normalize_name(
        "Drop: Example Bundle — Standard Edition"
    )
    assert name == "Example Bundle"
    assert "REMOVE_DROP_PREFIX" in actions
    assert "REMOVE_REDUNDANT_STANDARD_SUFFIX" in actions


def test_duplicate_foil_suffix_is_collapsed():
    module = load_module()
    name, actions = module.normalize_name(
        "Example - Traditional Foil Edition — Foil Edition"
    )
    assert name == "Example - Traditional Foil Edition"
    assert "COLLAPSE_DUPLICATE_FOIL_SUFFIX" in actions


def test_filename_version_artifact_is_removed():
    module = load_module()
    name, actions = module.normalize_name(
        "Secret Lair x Deadpool: "
        "FINAL_final_REALLYfinal_v7_USETHISONE(2)_Everything Bundle"
    )
    assert name == "Secret Lair x Deadpool: Everything Bundle"
    assert "REMOVE_FILENAME_VERSION_ARTIFACT" in actions


def test_live_collection_remains_disabled():
    module = load_module()
    row = module.normalize_row({
        "canonical_product_id": "A",
        "canonical_product_name": "Drop: Example — Standard Edition",
        "product_class": "SECRET_LAIR",
        "ebay_query": '"Drop: Example — Standard Edition" sealed',
    })
    assert row["query_review_status"] == "APPROVED_FOR_DRY_RUN"
    assert row["live_collection_allowed"] == "false"
