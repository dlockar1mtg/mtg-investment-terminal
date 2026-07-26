from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_mtg_marketplace_production.py"


def _map(path: Path, complete: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    group = "10" if complete else ""
    path.write_text(
        "box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\n"
        f"Example Box,1,3,{group}\n",
        encoding="utf-8",
    )
    return path


def _model(path: Path) -> Path:
    path.write_text(
        "box_name,current_price,fair_value_estimate,data_quality_score,liquidity_score,reprint_risk\n"
        "Example Box,100,130,80,70,20\n",
        encoding="utf-8",
    )
    return path


def _run(tmp_path: Path, product_map: Path, *extra: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    output = tmp_path / "latest.json"
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--product-map",
            str(product_map),
            "--reconciliation-search-root",
            str(evidence_root),
            "--model-input",
            str(_model(tmp_path / "model.csv")),
            "--output",
            str(output),
            *extra,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MTG_LIVE_EXECUTION": "false"},
    )
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_combined_dry_run_passes_with_complete_map(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _map(tmp_path / "map.csv"))
    assert result.returncode == 0
    assert payload["status"] == "DRY_RUN_PASS"
    assert payload["live_api_called"] is False
    assert payload["deal_rankings"][0]["signal"] == "BUY"


def test_combined_cycle_fails_closed_for_incomplete_tcgcsv_map(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _map(tmp_path / "map.csv", complete=False))
    assert result.returncode == 2
    assert payload["status"] == "INCOMPLETE"
    assert "TCGCSV_LANE_NOT_READY" in payload["reason_codes"]


def test_combined_cycle_materializes_unique_reconciled_map(tmp_path: Path) -> None:
    product_map = _map(tmp_path / "reference" / "map.csv", complete=False)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    snapshot = evidence_root / "snapshot.csv"
    snapshot.write_text(
        "tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\n"
        "1,1,999\n",
        encoding="utf-8",
    )
    output = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--product-map",
            str(product_map),
            "--reconciliation-search-root",
            str(evidence_root),
            "--model-input",
            str(_model(tmp_path / "model.csv")),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MTG_LIVE_EXECUTION": "false"},
    )
    assert result.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "DRY_RUN_PASS"
    assert payload["reconciliation"]["status"] == "PASS"
    runtime_map = Path(str(payload["runtime_product_map"]))
    with runtime_map.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["tcgcsv_group_id"] == "999"
    assert row["tcgcsv_category_id"] == "1"
    with product_map.open("r", encoding="utf-8", newline="") as handle:
        reference_row = next(csv.DictReader(handle))
    assert reference_row["tcgcsv_group_id"] == ""


def test_live_flag_is_blocked_without_environment_gate(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, _map(tmp_path / "map.csv"), "--live")
    assert result.returncode == 2
    assert payload["status"] == "SAFE_HOLD"
    assert payload["live_api_called"] is False
    assert "MTG_LIVE_EXECUTION_ENV_DISABLED" in payload["reason_codes"]
