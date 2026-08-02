from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts import build_collector_v1_evidence_tournament_reconstruction_plan as build

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_evidence_tournament_reconstruction_plan"


def test_evidence_tournament_reconstruction_plan_enforces_mtg_domain_boundary() -> None:
    assert build.main([]) == 0

    summary = json.loads(
        (OUT / "collector_v1_evidence_tournament_reconstruction_plan_summary.json").read_text(
            encoding="utf-8"
        )
    )
    matrix = pd.read_csv(
        OUT / "collector_v1_evidence_tournament_reconstruction_matrix.csv",
        dtype=str,
    ).fillna("")

    assert summary["status"] == "PASS_COLLECTOR_V1_EVIDENCE_TOURNAMENT_RECONSTRUCTION_PLAN"
    assert summary["governed_product_count"] == 50
    assert summary["required_horizons"] == ["90_day", "180_day", "365_day", "3_year", "5_year"]
    assert summary["product_horizon_rows"] == 250
    assert summary["reconstruction_execution_authorized"] is True
    assert summary["forecast_generation_authorized"] is False
    assert summary["ranking_generation_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False
    assert summary["critical_failures"] == []
    assert summary["checks"]["fixed_weights_not_required"] is True
    assert summary["checks"]["domain_ownership_is_separated"] is True
    assert summary["checks"]["all_outputs_owned_by_mtg"] is True
    assert summary["checks"]["uip_cannot_rewrite_mtg_outputs"] is True

    assert len(matrix) == 250
    assert matrix.groupby("tcgplayer_product_id")["horizon_id"].nunique().eq(5).all()
    assert matrix["mtg_owned_output"].str.lower().eq("true").all()
    assert matrix["uip_may_rewrite_output"].str.lower().eq("false").all()
    assert matrix["purchase_recommendation_authorized"].str.lower().eq("false").all()

    short = matrix[matrix["horizon_id"].isin(["90_day", "180_day", "365_day"])]
    long = matrix[matrix["horizon_id"].isin(["3_year", "5_year"])]
    assert short["model_tournament_required"].str.lower().eq("true").all()
    assert short["monte_carlo_required"].str.lower().eq("false").all()
    assert long["model_tournament_required"].str.lower().eq("true").all()
    assert long["monte_carlo_required"].str.lower().eq("true").all()
    assert matrix["supply_demand_ablation_required"].str.lower().eq("true").all()

    star_trek = matrix[matrix["tcgplayer_product_id"].eq("706142")]
    assert len(star_trek) == 5
    assert star_trek["comparable_selection_required"].str.lower().eq("true").all()
    assert star_trek["breakout_validation_required"].str.lower().eq("true").all()
