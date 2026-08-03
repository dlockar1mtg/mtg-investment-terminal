from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_final_universe_resolution.py"
SPEC = importlib.util.spec_from_file_location("final_universe_resolution", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_contract_keeps_all_downstream_authorities_disabled():
    contract = json.loads((ROOT / "config/mtg/standards/precollector_final_universe_resolution_contract_v1.json").read_text(encoding="utf-8"))
    controls = contract["certification_controls"]
    assert controls["forecast_generation_authorized"] is False
    assert controls["ranking_execution_authorized"] is False
    assert controls["purchase_recommendation_authorized"] is False
    assert controls["automatic_purchase_execution_authorized"] is False
    assert controls["owner_approval_required_before_freeze"] is True


def test_alias_authority_covers_all_prior_date_review_families():
    authority = json.loads((ROOT / "config/mtg/governance/precollector_release_alias_authority_v1.json").read_text(encoding="utf-8"))
    sources = {row["source_release_name"] for row in authority["aliases"]}
    required = {
        "7th Edition", "8th Edition", "9th Edition", "10th Edition",
        "Alpha Edition", "Beta Edition", "Magic 2010 (M10)", "Magic 2015 (M15)",
        "Mystery Booster: Convention Edition Exclusives", "Mystery Booster: Retail Exclusives",
    }
    assert required <= sources


def test_product_release_date_parsing_is_product_level():
    value = "{'isPresale': False, 'releasedOn': '2020-03-13T00:00:00', 'note': None}"
    assert MODULE.parse_product_release_date(value) == "2020-03-13"
    assert MODULE.parse_product_release_date("not a payload") == ""


def test_fresh_delta_reapplies_approved_format_exclusions():
    delta = pd.DataFrame([
        {"canonical_product_id": "tcgplayer:1", "product_name": "Old Set - Draft Booster Box", "reconciliation_group_id": "10"},
        {"canonical_product_id": "tcgplayer:2", "product_name": "Old Set - Collector Booster Box", "reconciliation_group_id": "10"},
        {"canonical_product_id": "tcgplayer:3", "product_name": "Old Set - Booster Box Case", "reconciliation_group_id": "10"},
        {"canonical_product_id": "tcgplayer:4", "product_name": "Older Set - Booster Box", "reconciliation_group_id": "20"},
    ])
    full = delta.copy()
    result = MODULE.classify_fresh_delta(delta, full)
    reasons = dict(zip(result["canonical_product_id"], result["fresh_resolution_reason"]))
    assert reasons["tcgplayer:1"] == "DRAFT_BOOSTER_PRODUCT"
    assert reasons["tcgplayer:2"] == "COLLECTOR_BOOSTER_PRODUCT"
    assert reasons["tcgplayer:3"] == "BOOSTER_BOX_CASE"
    assert reasons["tcgplayer:4"] == "FRESH_ONLY_BOX_REQUIRES_OWNER_AND_FORMAT_CONFIRMATION"


def test_release_with_collector_option_is_not_admitted():
    delta = pd.DataFrame([
        {"canonical_product_id": "tcgplayer:1", "product_name": "Example - Set Booster Box", "reconciliation_group_id": "10"},
    ])
    full = pd.DataFrame([
        {"canonical_product_id": "tcgplayer:1", "product_name": "Example - Set Booster Box", "reconciliation_group_id": "10"},
        {"canonical_product_id": "tcgplayer:2", "product_name": "Example - Collector Booster Box", "reconciliation_group_id": "10"},
    ])
    result = MODULE.classify_fresh_delta(delta, full)
    assert result.iloc[0]["fresh_resolution_status"] == "OWNER_EXCLUSION_RECOMMENDED"
    assert result.iloc[0]["fresh_resolution_reason"] == "RELEASE_HAS_COLLECTOR_OPTION"


def test_tcgcsv_group_creation_dates_remain_forbidden():
    contract = json.loads((ROOT / "config/mtg/standards/precollector_final_universe_resolution_contract_v1.json").read_text(encoding="utf-8"))
    assert contract["release_date_controls"]["tcgcsv_group_creation_date_allowed"] is False
    assert contract["release_date_controls"]["guessed_dates_allowed"] is False
