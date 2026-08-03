from __future__ import annotations

import json
from pathlib import Path

from scripts import activate_collector_v1_august1_current_data_authority as activation
from scripts import reconcile_collector_v1_august1_price_observation_lineage as lineage

ROOT = Path(__file__).resolve().parents[1]


def test_august1_price_lineage_and_authority_activation() -> None:
    assert lineage.main([]) == 0
    lineage_summary = json.loads((ROOT / "data/governance/permanence/certification/collector_v1_august1_price_observation_lineage/collector_v1_august1_price_observation_lineage_summary.json").read_text(encoding="utf-8"))
    assert lineage_summary["status"] == "PASS_COLLECTOR_V1_AUGUST1_PRICE_OBSERVATION_LINEAGE"
    assert lineage_summary["critical_failures"] == []
    assert lineage_summary["model_rebuild_authorized"] is True
    assert lineage_summary["purchase_recommendations_authorized"] is False

    assert activation.main([]) == 0
    authority = json.loads((ROOT / "data/governance/permanence/authority/collector_v1_current_data_authority_active.json").read_text(encoding="utf-8"))
    assert authority["status"] == "ACTIVE_AUGUST1_SNAPSHOT_BOUND_MODEL_INPUT_AUTHORITY"
    assert authority["source_snapshot_id"] == lineage.SNAPSHOT_ID
    assert authority["model_input_authorized"] is True
    assert authority["snapshot_bound_model_rebuild_authorized"] is True
    assert authority["purchase_recommendations_authorized"] is False
    assert authority["production_forecasting_authorized"] is False
    assert authority["uip_delivery_authorized"] is False
