import json
from pathlib import Path

import pandas as pd

from scripts.build_collector_v1_historical_source_precedence_registry import main

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "data/governance/permanence/certification/collector_v1_historical_source_precedence"


def test_source_precedence_registry_builds_fail_closed():
    assert main(strict=True) == 0
    summary = json.loads((OUTDIR / "collector_v1_historical_source_precedence_summary.json").read_text())
    rows = pd.read_csv(OUTDIR / "collector_v1_historical_source_precedence_registry.csv")
    assert len(rows) == summary["candidate_source_count"]
    assert summary["identity_authority_source_count"] >= 1
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_portfolio_sources_are_not_historical_price_authorities():
    main(strict=True)
    rows = pd.read_csv(OUTDIR / "collector_v1_historical_source_precedence_registry.csv")
    portfolio = rows[rows["source_path"].str.contains("portfolio|owned_inventory|positions", case=False, regex=True)]
    assert not portfolio.empty
    assert set(portfolio["source_role"]) == {"EXCLUDED_OPERATIONAL_OR_PORTFOLIO"}
    assert not portfolio["usable_for_price_history"].astype(bool).any()


def test_listing_evidence_is_corroborating_not_aggregated_price_authority():
    main(strict=True)
    rows = pd.read_csv(OUTDIR / "collector_v1_historical_source_precedence_registry.csv")
    listings = rows[rows["source_path"].str.contains("ebay_listing_match_results", case=False, regex=False)]
    assert not listings.empty
    assert set(listings["source_role"]) == {"CORROBORATING_OBSERVATION"}
    assert not listings["usable_for_price_history"].astype(bool).any()
