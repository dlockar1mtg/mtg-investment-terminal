from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_precollector_universe_reconciliation.py"
SPEC = importlib.util.spec_from_file_location("precollector_reconciliation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_contract_is_evidence_only_and_downstream_disabled():
    contract = json.loads((ROOT / "config/mtg/standards/precollector_universe_reconciliation_contract_v1.json").read_text(encoding="utf-8"))
    controls = contract["controls"]
    assert controls["fresh_sources_may_replace_certified_universe_automatically"] is False
    assert controls["unmatched_wizards_release_date_may_be_guessed"] is False
    assert controls["source_conflicts_may_be_silently_resolved"] is False
    assert controls["forecast_generation_authorized"] is False
    assert controls["ranking_execution_authorized"] is False
    assert controls["purchase_recommendation_authorized"] is False
    assert controls["automatic_purchase_execution_authorized"] is False


def test_contract_binds_certified_august1_hash():
    contract = json.loads((ROOT / "config/mtg/standards/precollector_universe_reconciliation_contract_v1.json").read_text(encoding="utf-8"))
    source = ROOT / contract["sources"]["certified_august1_products"]
    assert source.exists()
    assert MODULE.sha256_file(source) == contract["sources"]["certified_august1_sha256"]


def test_candidate_key_normalizes_box_phrasing_without_erasing_set():
    assert MODULE.candidate_key("Magic: The Gathering Modern Masters Factory Sealed Booster Box") == "modern masters"
    assert MODULE.candidate_key("Urza's Saga Booster Display Box") == "urza s saga"


def test_reconciliation_requires_date_review_without_wizards_match():
    existing = pd.DataFrame([{
        "canonical_product_id": "tcgplayer:1",
        "product_name": "Example Booster Box",
        "release_or_group_id": "10",
        "release_or_group_name": "Example",
        "initial_inclusion_status": "INCLUDED_CANDIDATE",
    }])
    fresh = pd.DataFrame([{
        "canonical_product_id": "tcgplayer:1",
        "product_name": "Example Booster Box",
        "reconciliation_group_id": "10",
        "reconciliation_group_name": "Example",
        "reconciliation_source_url": "https://example.invalid",
    }])
    wizards = pd.DataFrame(columns=[
        "normalized_release_key", "wizards_release_name", "official_release_date",
        "wizards_source_url", "wizards_date_conflict_indicator",
    ])
    outputs = MODULE.reconcile(existing, fresh, wizards)
    row = outputs["precollector_reconciled_candidate_universe.csv"].iloc[0]
    assert row["reconciliation_status"] == "REQUIRES_RELEASE_DATE_REVIEW"


def test_reconciliation_does_not_authorize_forecasts():
    standard = (ROOT / "docs/standards/mtg/MTG_FORECASTING_STANDARD.md").read_text(encoding="utf-8")
    assert "Forecast generation and purchase authorization remain separate." in standard
