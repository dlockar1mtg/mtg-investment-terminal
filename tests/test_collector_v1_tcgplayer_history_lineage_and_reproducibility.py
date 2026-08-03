from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_tcgplayer_history_lineage_reproducibility_contract_v1.json"
AUDIT = ROOT / "scripts/audit_collector_v1_tcgplayer_history_lineage_and_reproducibility.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8-sig"))


def test_contract_and_audit_exist() -> None:
    assert CONTRACT.is_file()
    assert AUDIT.is_file()


def test_audit_script_compiles() -> None:
    ast.parse(AUDIT.read_text(encoding="utf-8-sig"))


def test_governing_snapshot_is_exact() -> None:
    contract = load_contract()
    snapshot = contract["governing_snapshot"]
    assert snapshot["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert snapshot["operating_date"] == "2026-08-01"
    assert snapshot["timezone"] == "America/Chicago"
    assert snapshot["source_bundle_sha256"] == "7688afbd6dfb4483c0a316dad6a2a05458944434a91a3f714568e5f4a10c7890"
    assert snapshot["certified_product_count"] == 50


def test_provider_roles_supersede_prior_two_provider_price_scope() -> None:
    supersession = load_contract()["supersession"]
    assert supersession["supersedes_two_provider_historical_price_reconstruction_requirement"] is True
    assert supersession["tcgplayer_historical_market_price_authority_candidate"] is True
    assert supersession["ebay_historical_market_price_reconstruction_required"] is False
    assert supersession["ebay_role"] == "CERTIFIED_SUPPLY_DEMAND_LIQUIDITY_BASELINE"


def test_candidate_classifications_are_exact() -> None:
    assert load_contract()["candidate_classifications"] == [
        "CERTIFIABLE_EXISTING_TCGPLAYER_HISTORY",
        "REPRODUCIBLE_TCGPLAYER_HISTORY_SOURCE",
        "DERIVED_ONLY_NOT_AUTHORITY",
        "STALE_OUTPUT_NOT_PERMITTED",
        "IDENTITY_MISMATCH",
        "UNRESOLVED_LINEAGE",
    ]


def test_downstream_authorizations_remain_false() -> None:
    authorization = load_contract()["authorization"]
    assert authorization["lineage_and_reproducibility_audit_authorized"] is True
    for key in (
        "historical_reconstruction_execution_authorized",
        "historical_observation_ledger_build_authorized",
        "raw_historical_price_authority_certified",
        "historical_coverage_assessment_authorized",
        "lifecycle_panel_build_authorized",
        "model_tournament_authorized",
        "production_forecasting_authorized",
        "uip_delivery_authorized",
        "purchase_recommendations_authorized",
    ):
        assert authorization[key] is False


def test_bounded_targets_are_exact() -> None:
    assert load_contract()["bounded_targets"] == [
        "data/operations/mtg_universal_history_ledger/universal_mtg_daily_consolidated_ledger.csv",
        "data/staging/purchase_refresh/2026-07-31/collector_history_rebuilt/product_master_model_input.csv",
        "scripts/build_canonical_governed_history.py",
        "scripts/certify_collector_booster_history.py",
        "scripts/run_collector_history_semantic_gate.py",
    ]
