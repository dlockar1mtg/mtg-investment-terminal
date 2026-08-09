from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_canonical_universe_freeze.py"
CONTRACT = ROOT / "config/mtg/standards/precollector_canonical_universe_freeze_contract_v1.json"
APPROVAL = ROOT / "config/mtg/governance/precollector_canonical_universe_owner_approval_v1.json"

SPEC = importlib.util.spec_from_file_location("precollector_freeze", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_and_owner_approval_are_fail_closed() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    assert contract["required_input"]["expected_product_count"] == 124
    assert contract["required_input"]["expected_fresh_exclusion_count"] == 80
    assert approval["decision"] == "APPROVE_CERTIFIED_V7_PRECOLLECTOR_UNIVERSE_FOR_CANONICAL_FREEZE"
    assert approval["certified_v7_review_zip_sha256"] == "1481a55307febda93375954d5fd1eb7a59f33dd53b8ed197a90d19016b691833"
    assert approval["controls"]["forecast_generation_authorized"] is False
    assert approval["controls"]["purchase_recommendation_authorized"] is False


def test_build_canonical_preserves_identity_and_authority() -> None:
    ready = pd.DataFrame({
        "canonical_product_id": ["tcgplayer:1"],
        "governed_asset_key": ["release|box"],
        "product_name_august1": ["Example - Booster Box"],
        "release_or_group_name": ["Example"],
        "governed_release_date": ["2000-01-01"],
        "release_date_authority": ["MTGJSON_SECONDARY"],
    })
    approval = {"approval_id": "approval-test"}
    result = MODULE.build_canonical(ready, approval)
    assert result.loc[0, "canonical_product_id"] == "tcgplayer:1"
    assert result.loc[0, "language"] == "English"
    assert result.loc[0, "scope_status"] == "CANONICAL_INCLUDED_OWNER_APPROVED"


def test_validate_rejects_duplicate_identity() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    canonical = pd.DataFrame({
        "canonical_product_id": ["x", "x"],
        "governed_asset_key": ["a", "b"],
        "product_name": ["A Booster Box", "B Booster Box"],
        "release_name": ["A", "B"],
        "governed_release_date": ["2000-01-01", "2001-01-01"],
        "release_date_authority": ["A", "B"],
        "language": ["English", "English"],
        "configuration": ["INDIVIDUAL_FACTORY_SEALED_BOOSTER_BOX"] * 2,
        "scope_status": ["CANONICAL_INCLUDED_OWNER_APPROVED"] * 2,
        "owner_approval_id": [approval["approval_id"]] * 2,
    })
    exclusions = pd.DataFrame({"fresh_resolution_status": ["OWNER_EXCLUSION_RECOMMENDED"] * 80})
    with pytest.raises(RuntimeError, match="DUPLICATE_CANONICAL_PRODUCT_ID"):
        MODULE.validate(canonical, exclusions, contract, approval)


def test_validate_rejects_prohibited_configuration() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    rows = []
    for index in range(124):
        rows.append({
            "canonical_product_id": f"id-{index}",
            "governed_asset_key": f"key-{index}",
            "product_name": "Example Draft Booster Box" if index == 0 else f"Example {index} Booster Box",
            "release_name": f"Release {index}",
            "governed_release_date": "2000-01-01",
            "release_date_authority": "TEST",
            "language": "English",
            "configuration": "INDIVIDUAL_FACTORY_SEALED_BOOSTER_BOX",
            "scope_status": "CANONICAL_INCLUDED_OWNER_APPROVED",
            "owner_approval_id": approval["approval_id"],
        })
    exclusions = pd.DataFrame({"fresh_resolution_status": ["OWNER_EXCLUSION_RECOMMENDED"] * 80})
    with pytest.raises(RuntimeError, match="PROHIBITED_PRODUCT_IN_CANONICAL_UNIVERSE"):
        MODULE.validate(pd.DataFrame(rows), exclusions, contract, approval)
