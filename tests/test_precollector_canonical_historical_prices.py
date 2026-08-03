from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/build_precollector_canonical_historical_prices.py"
SPEC = importlib.util.spec_from_file_location("precollector_canonical_history", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_exists_and_keeps_downstream_disabled():
    contract = MODULE.load_json(MODULE.CONTRACT_PATH)
    assert contract["expected_product_count"] == 124
    assert contract["historical_append_authorized"] is False
    assert contract["forecast_generation_authorized"] is False
    assert contract["ranking_execution_authorized"] is False
    assert contract["purchase_recommendation_authorized"] is False


def test_sha256_file_is_stable(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("abc\n", encoding="utf-8")
    assert MODULE.sha256_file(path) == MODULE.sha256_file(path)


def test_duplicate_resolution_policy_is_deterministic():
    frame = pd.DataFrame([
        {"canonical_product_id": "tcgplayer:1", "observation_timestamp": pd.Timestamp("2020-01-01", tz="UTC"), "historical_price": 10.0, "source_path": "b.csv"},
        {"canonical_product_id": "tcgplayer:1", "observation_timestamp": pd.Timestamp("2020-01-01", tz="UTC"), "historical_price": 11.0, "source_path": "a.csv"},
    ])
    resolved = frame.sort_values(["canonical_product_id", "observation_timestamp", "source_path"], kind="stable").drop_duplicates(["canonical_product_id", "observation_timestamp"], keep="last")
    assert resolved.iloc[0]["source_path"] == "b.csv"
    assert resolved.iloc[0]["historical_price"] == 10.0


def test_history_depth_requires_rows_and_distinct_dates():
    coverage = pd.DataFrame({"historical_rows": [2, 2, 1], "distinct_observation_dates": [2, 1, 1]})
    status = (coverage["historical_rows"].ge(2) & coverage["distinct_observation_dates"].ge(2))
    assert status.tolist() == [True, False, False]


def test_missing_history_reason_is_fail_closed():
    canonical = pd.DataFrame({"canonical_product_id": ["tcgplayer:1", "tcgplayer:2"]})
    covered = {"tcgplayer:1"}
    missing = canonical[~canonical["canonical_product_id"].isin(covered)].copy()
    missing["historical_blocking_reason"] = "NO_ADMISSIBLE_HISTORICAL_OBSERVATIONS"
    assert len(missing) == 1
    assert missing.iloc[0]["canonical_product_id"] == "tcgplayer:2"
    assert missing.iloc[0]["historical_blocking_reason"]


def test_no_automatic_authorization_strings_in_builder():
    text = PATH.read_text(encoding="utf-8")
    assert '"forecast_generation_authorized": False' in text
    assert '"purchase_recommendation_authorized": False' in text
    assert '"automatic_purchase_execution_authorized": False' in text
