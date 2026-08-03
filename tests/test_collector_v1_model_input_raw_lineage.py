from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trace_collector_v1_model_input_raw_lineage.py"
OUTPUT = ROOT / "data" / "governance" / "permanence" / "certification" / "collector_v1_model_input_raw_lineage"
SUMMARY = OUTPUT / "collector_v1_model_input_raw_lineage_summary.json"
CANDIDATES = OUTPUT / "collector_v1_model_input_lineage_candidates.csv"
REFERENCES = OUTPUT / "collector_v1_model_input_code_references.csv"


def test_lineage_trace_runs_fail_closed() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT), "--strict"], cwd=ROOT, check=False)
    assert result.returncode == 0
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS_COLLECTOR_V1_MODEL_INPUT_RAW_LINEAGE_TRACE"
    assert summary["raw_historical_price_authority_certified"] is False
    assert summary["historical_coverage_assessment_authorized"] is False
    assert summary["lifecycle_panel_build_authorized"] is False
    assert summary["model_tournament_authorized"] is False
    assert summary["purchase_recommendations_authorized"] is False


def test_lineage_outputs_are_auditable() -> None:
    assert CANDIDATES.exists()
    assert REFERENCES.exists()
    with CANDIDATES.open("r", encoding="utf-8", newline="") as handle:
        fields = set(next(csv.DictReader(handle), {}).keys())
    assert {
        "candidate_path",
        "source_sha256",
        "byte_identical_to_target",
        "schema_overlap_ratio",
        "likely_copy_or_promoted_artifact",
    }.issubset(fields)


def test_contract_prohibits_unresolved_authority() -> None:
    contract = json.loads((ROOT / "config" / "mtg" / "standards" / "collector_model_input_raw_lineage_contract_v1.json").read_text(encoding="utf-8"))
    assert contract["authorization_policy"]["historical_price_authority_requires_raw_lineage_certified"] is True
    assert "unresolved_lineage_can_become_price_authority" in contract["prohibited_assumptions"]
