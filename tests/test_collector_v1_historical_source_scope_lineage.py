from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.adjudicate_collector_v1_historical_source_scope_lineage import main

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_v1_historical_source_scope_lineage"


def test_scope_lineage_adjudication_certifies() -> None:
    assert main(["--strict"]) == 0
    summary = json.loads((OUT / "collector_v1_historical_source_scope_lineage_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_HISTORICAL_SOURCE_SCOPE_LINEAGE_ADJUDICATION"
    assert summary["source_scope_lineage_adjudication_certified"] is True
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_only_collector_bound_canonical_sources_become_panel_candidates() -> None:
    main(["--strict"])
    frame = pd.read_csv(OUT / "collector_v1_historical_source_scope_lineage_adjudication.csv")
    candidates = frame[frame["panel_candidate"].eq(True)]
    assert len(candidates) > 0
    assert candidates["collector_scope_state"].eq("COLLECTOR_BOUND").all()
    assert candidates["canonical_representative"].eq(True).all()
    assert candidates["lineage_eligible"].eq(True).all()
    assert not candidates["source_path"].str.contains("secret_lair", case=False, na=False).any()
    assert not candidates["source_path"].str.contains("pre_collector", case=False, na=False).any()


def test_one_canonical_representative_per_lineage_family() -> None:
    main(["--strict"])
    frame = pd.read_csv(OUT / "collector_v1_historical_source_scope_lineage_adjudication.csv")
    counts = frame.groupby("lineage_family_id")["canonical_representative"].sum()
    assert counts.eq(1).all()


def test_copy_and_migration_artifacts_are_not_panel_candidates() -> None:
    main(["--strict"])
    frame = pd.read_csv(OUT / "collector_v1_historical_source_scope_lineage_adjudication.csv")
    copies = frame[frame["copy_or_migration_artifact"].eq(True)]
    assert not copies["panel_candidate"].eq(True).any()
