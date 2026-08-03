from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_semantic_cleanup_release_authority.py"
SPEC = importlib.util.spec_from_file_location("precollector_semantic_cleanup", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_contract_preserves_source_hierarchy_and_disables_downstream():
    contract = json.loads((ROOT / "config/mtg/standards/precollector_semantic_cleanup_release_authority_contract_v1.json").read_text(encoding="utf-8"))
    hierarchy = contract["source_hierarchy"]
    assert hierarchy["release_date_primary"].startswith("Wizards")
    assert hierarchy["release_date_secondary"].startswith("MTGJSON")
    assert hierarchy["tcgcsv_published_on_release_date_authorized"] is False
    controls = contract["certification_controls"]
    assert controls["forecast_generation_authorized"] is False
    assert controls["ranking_execution_authorized"] is False
    assert controls["purchase_recommendation_authorized"] is False
    assert controls["automatic_purchase_execution_authorized"] is False


def test_semantic_classifier_excludes_cases_and_non_booster_displays():
    assert MODULE.semantic_classification("Aether Revolt - Booster Box Case") == (
        "EXCLUDED_CONFIGURATION", "BOOSTER_BOX_CASE"
    )
    assert MODULE.semantic_classification("Guilds of Ravnica - Theme Booster Display Box") == (
        "EXCLUDED_CONFIGURATION", "NON_BOOSTER_DISPLAY"
    )
    assert MODULE.semantic_classification("War of the Spark Booster Box") == (
        "SEMANTIC_CANDIDATE", "INDIVIDUAL_BOOSTER_BOX"
    )


def test_release_authority_prefers_wizards_and_uses_secondary_without_guessing():
    reconciled = pd.DataFrame([
        {
            "canonical_product_id": "tcgplayer:1",
            "reconciliation_group_name": "Example Set",
            "official_release_date": "2020-01-01",
        },
        {
            "canonical_product_id": "tcgplayer:2",
            "reconciliation_group_name": "Older Set",
            "official_release_date": None,
        },
        {
            "canonical_product_id": "tcgplayer:3",
            "reconciliation_group_name": "Unknown Set",
            "official_release_date": None,
        },
    ])
    secondary = pd.DataFrame([
        {"normalized_release_key": "example set", "secondary_release_name": "Example Set", "secondary_release_date": "2020-01-01", "secondary_set_code": "EX"},
        {"normalized_release_key": "older set", "secondary_release_name": "Older Set", "secondary_release_date": "1999-02-03", "secondary_set_code": "OLD"},
    ])
    result = MODULE.build_release_authority(reconciled, secondary)
    assert result.loc[0, "release_date_authority"] == "WIZARDS_OFFICIAL"
    assert result.loc[1, "release_date_authority"] == "MTGJSON_SECONDARY"
    assert result.loc[2, "release_date_authority"] == "UNRESOLVED"
    assert result.loc[2, "governed_release_date"] == ""


def test_release_date_disagreement_fails_to_conflict():
    reconciled = pd.DataFrame([
        {
            "canonical_product_id": "tcgplayer:1",
            "reconciliation_group_name": "Example Set",
            "official_release_date": "2020-01-01",
        }
    ])
    secondary = pd.DataFrame([
        {"normalized_release_key": "example set", "secondary_release_name": "Example Set", "secondary_release_date": "2020-02-01", "secondary_set_code": "EX"},
    ])
    result = MODULE.build_release_authority(reconciled, secondary)
    assert result.loc[0, "release_date_authority"] == "SOURCE_CONFLICT"
    assert result.loc[0, "governed_release_date"] == ""
    assert bool(result.loc[0, "release_date_conflict_indicator"]) is True
