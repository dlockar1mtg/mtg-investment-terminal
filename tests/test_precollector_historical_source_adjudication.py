from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_historical_source_adjudication.py"
SPEC = importlib.util.spec_from_file_location("precollector_historical_source_adjudication", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_normalize_id_handles_prefix_and_float_suffix() -> None:
    assert MODULE.normalize_id("tcgplayer:123.0") == "123"


def test_first_column_is_case_insensitive() -> None:
    assert MODULE.first_column(["ProductId", "Date"], ["productId"]) == "ProductId"


def test_contract_preserves_downstream_blocks() -> None:
    contract = MODULE.load_json(MODULE.CONTRACT_PATH)
    assert contract["historical_append_authorized"] is False
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False
    assert contract["automatic_purchase_execution_authorized"] is False


def test_contract_requires_two_candidate_sources() -> None:
    contract = MODULE.load_json(MODULE.CONTRACT_PATH)
    assert contract["expected_candidate_source_count"] == 2


def test_contract_requires_repeated_product_history() -> None:
    contract = MODULE.load_json(MODULE.CONTRACT_PATH)
    assert contract["minimum_rows_per_covered_product"] >= 2
    assert contract["minimum_distinct_observation_dates"] >= 2


def test_normalize_id_blank_safe() -> None:
    assert MODULE.normalize_id(None) == ""
    assert MODULE.normalize_id(pd.NA) == ""


def test_missing_contract_raises() -> None:
    with pytest.raises(FileNotFoundError):
        MODULE.load_json(ROOT / "does_not_exist.json")
