from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/repair_precollector_live_summary_matcher_metadata.py"


def load_module():
    spec = importlib.util.spec_from_file_location("repair_precollector_live_summary_matcher_metadata", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_is_bound_to_certified_august_3_run_and_matcher():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'EXPECTED_RUN_ID = "EBAY20260803T221111Z"' in text
    assert 'EXPECTED_MATCHER_VERSION = "precision-v3-universal"' in text
    assert "identity_match_listing.__module__" in text
    assert 'summary["matcher_fail_closed"] = True' in text
    assert '"counts_modified": False' in text
    assert '"listing_rows_modified": False' in text


def test_module_imports():
    module = load_module()
    assert callable(module.main)
    assert module.EXPECTED_LISTING_ROWS == 7488
    assert module.EXPECTED_ACCEPTED_ROWS == 936
    assert module.EXPECTED_REVIEW_ROWS == 207
    assert module.EXPECTED_REJECTED_ROWS == 6345
