from __future__ import annotations

import json
from pathlib import Path

from scripts import verify_collector_v1_snapshot_bound_authorities as verifier


def test_certified_august_1_authorities_verify_fail_closed() -> None:
    result = verifier.main([])
    assert result == 0

    output = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "governance"
        / "permanence"
        / "certification"
        / "collector_v1_snapshot_bound_authority_verification"
        / "collector_v1_snapshot_bound_authority_verification_summary.json"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["source_snapshot_id"] == verifier.EXPECTED_SNAPSHOT_ID
    assert payload["verified_for_snapshot_bound_model_rebuild"] is True
    assert payload["purchase_recommendations_authorized"] is False
    assert payload["critical_failures"] == []

    required = {
        "price",
        "identity",
        "listing",
        "supply",
        "route",
        "history",
        "feature",
    }
    assert required == set(payload["authorities"])
    assert all(item["hash_matches"] for item in payload["authorities"].values())
