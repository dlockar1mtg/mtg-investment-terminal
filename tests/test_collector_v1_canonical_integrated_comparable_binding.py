from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_canonical_identity_lineage_recertification_contract_v1.json"
INTEGRATION_SUMMARY = ROOT / "data/governance/permanence/certification/collector_v1_lorwyn_comparable_authority_integration/collector_lorwyn_comparable_authority_integration_summary.json"
INTEGRATED_AUTHORITY = ROOT / "data/governance/permanence/certification/collector_v1_lorwyn_comparable_authority_integration/collector_integrated_comparable_pool_authority.csv"


def test_canonical_contract_binds_to_integrated_comparable_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["contract_version"] == "1.0.2"
    assert contract["authorities"]["comparable_pool"] == (
        "data/governance/permanence/certification/"
        "collector_v1_lorwyn_comparable_authority_integration/"
        "collector_integrated_comparable_pool_authority.csv"
    )
    assert contract["governance"]["integrated_comparable_authority_required"] is True


def test_integrated_comparable_authority_is_certified_and_present() -> None:
    assert INTEGRATED_AUTHORITY.is_file()
    assert INTEGRATION_SUMMARY.is_file()
    summary = json.loads(INTEGRATION_SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_LORWYN_COMPARABLE_AUTHORITY_INTEGRATION"
    assert summary["integrated_rows"] == 121
    assert summary["integrated_targets"] == 24
    assert summary["integrated_unique_pairs"] == 121
    assert not summary["critical_failures"]
    assert summary["projection_authorized"] is False
    assert summary["production_forecast_authorized"] is False
    assert summary["ranking_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
