from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_candidate_universe_inventory_contract_v1.json"


def test_candidate_universe_is_bound_to_certified_august1_operational_snapshot():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    discovery = contract["source_discovery"]

    assert contract["contract_version"] == "1.0.1"
    assert discovery["roots"] == [
        "data/operations/mtg_source_discovery/tcgcsv_snapshots/20260801T211201Z"
    ]
    assert "data" not in discovery["roots"]
    assert "data/staging" not in discovery["roots"]
    assert "staging copies" in discovery["excluded_source_classes"]
    assert "certified August 1 operational TCGCSV snapshot root only" in discovery["selection_rule"]


def test_source_binding_does_not_authorize_downstream_decisions():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    controls = contract["certification_controls"]

    assert controls["forecast_generation_authorized"] is False
    assert controls["ranking_execution_authorized"] is False
    assert controls["purchase_recommendation_authorized"] is False
    assert controls["automatic_purchase_execution_authorized"] is False
