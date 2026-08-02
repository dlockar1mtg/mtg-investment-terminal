from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_collector_v1_current_foundation_contract as audit


def test_current_foundation_contract_discovery_is_snapshot_bound() -> None:
    result = audit.main([])
    assert result == 0

    output = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "governance"
        / "permanence"
        / "certification"
        / "collector_v1_current_foundation_contract_audit"
        / "collector_v1_current_foundation_contract_audit_summary.json"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["source_snapshot_id"] == audit.SNAPSHOT_ID
    assert payload["purchase_recommendations_authorized"] is False
    assert set(payload["authorities"]) == set(audit.AUTHORITY_ROLES)
    assert payload["authorities"]["price"]["row_count"] == 50
    assert payload["authorities"]["identity"]["row_count"] == 50
    assert payload["authorities"]["supply"]["row_count"] == 50
    assert payload["authorities"]["feature"]["row_count"] == 50
    assert payload["checks"]["all_authorities_profiled"] is True


def test_contract_aliases_include_required_semantics() -> None:
    assert "investment_product_id" in audit.KEY_ALIASES
    assert "current_price" in audit.PRICE_ALIASES
    assert "accepted_listing_count" in audit.LISTING_COUNT_ALIASES
    assert "forecast_method" in audit.ROUTE_ALIASES
