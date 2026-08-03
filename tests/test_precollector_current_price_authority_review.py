from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_current_price_authority_review.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_current_price_authority_review_contract_v1.json"
SPEC = importlib.util.spec_from_file_location("precollector_current_price_authority_review", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def base_frame(rows: int = 124) -> pd.DataFrame:
    return pd.DataFrame({
        "tcgplayer_product_id": [str(i) for i in range(rows)],
        "current_price_authority_status": ["CURRENT_PRICE_AUTHORITY_CANDIDATE"] * rows,
        "market_price": [100.0] * rows,
        "price_selection_status": ["NORMAL_SUBTYPE_UNIQUE"] * rows,
        "admission_status": ["PRICE_CANDIDATE"] * rows,
        "observation_age_hours": [1.0] * rows,
        "blocking_reasons": [""] * rows,
    })


def test_contract_is_fail_closed() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["expected_product_count"] == 124
    assert contract["controls"]["blocked_products_admitted"] is False
    assert contract["controls"]["forecast_generation_authorized"] is False
    assert contract["controls"]["purchase_recommendation_authorized"] is False


def test_validate_accepts_clean_authority() -> None:
    MODULE.validate(base_frame(), json.loads(CONTRACT.read_text(encoding="utf-8")))


def test_validate_rejects_duplicate_product_id() -> None:
    frame = base_frame()
    frame.loc[1, "tcgplayer_product_id"] = frame.loc[0, "tcgplayer_product_id"]
    with pytest.raises(RuntimeError, match="DUPLICATE_CURRENT_PRICE_PRODUCT_ID"):
        MODULE.validate(frame, json.loads(CONTRACT.read_text(encoding="utf-8")))


def test_validate_rejects_nonpositive_authorized_price() -> None:
    frame = base_frame()
    frame.loc[0, "market_price"] = 0
    with pytest.raises(RuntimeError, match="NONPOSITIVE_MARKET_PRICE_IN_AUTHORITY"):
        MODULE.validate(frame, json.loads(CONTRACT.read_text(encoding="utf-8")))


def test_validate_rejects_blocked_without_reason() -> None:
    frame = base_frame()
    frame.loc[0, "current_price_authority_status"] = "BLOCKED"
    frame.loc[0, "blocking_reasons"] = ""
    with pytest.raises(RuntimeError, match="BLOCKED_PRODUCT_WITHOUT_REASON"):
        MODULE.validate(frame, json.loads(CONTRACT.read_text(encoding="utf-8")))


def test_split_reasons() -> None:
    assert MODULE.split_reasons("A;B;;") == ["A", "B"]
