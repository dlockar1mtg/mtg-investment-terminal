from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import audit_collector_v1_forecast_ranking_execution_readiness as audit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_forecast_ranking_execution_readiness"


def test_forecast_ranking_readiness_preserves_charter_boundary() -> None:
    assert audit.main([]) == 0
    summary = json.loads((OUT / "collector_v1_forecast_ranking_execution_readiness_summary.json").read_text(encoding="utf-8"))
    matrix = pd.read_csv(OUT / "collector_v1_forecast_ranking_product_readiness.csv", dtype=str).fillna("")

    assert summary["governed_product_count"] == 50
    assert summary["forecast_horizons_years"] == [1, 3, 5]
    assert summary["scenario_names"] == ["DOWNSIDE", "BASE", "UPSIDE"]
    assert summary["checks"]["foundation_certified"] is True
    assert summary["checks"]["all_products_remain_forecast_required"] is True
    assert summary["checks"]["all_methods_supported"] is True
    assert summary["checks"]["all_direct_routes_have_history"] is True
    assert summary["checks"]["purchase_recommendations_remain_unauthorized"] is True
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["integrity_failures"] == []
    assert summary["status"] in {
        "PASS_COLLECTOR_V1_FORECAST_RANKING_EXECUTION_READY",
        "READY_FOR_GOVERNED_NUMERICAL_EXECUTION_POLICY",
    }

    assert len(matrix) == 50
    assert matrix["tcgplayer_product_id"].is_unique
    assert matrix["forecast_output_required"].str.lower().eq("true").all()
    assert matrix["purchase_recommendation_authorized"].str.lower().eq("false").all()

    star_trek = matrix[matrix["tcgplayer_product_id"].eq("706142")]
    assert len(star_trek) == 1
    assert star_trek.iloc[0]["forecast_method"] == "COMPARABLE_PRODUCT_ADJUSTED"
    assert star_trek.iloc[0]["comparable_route"].lower() == "true"
    assert star_trek.iloc[0]["forecast_output_required"].lower() == "true"
