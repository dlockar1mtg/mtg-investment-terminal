from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_mtg_marketplace_production.py"


def _map(path: Path, complete: bool = True) -> Path:
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


def test_combined_dry_run_passes_with_complete_map(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--product-map", str(_map(tmp_path / "map.csv")),
            "--model-input", str(_model(tmp_path / "model.csv")),
            "--output", str(output),
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
    assert payload["live_api_called"] is False
    assert payload["deal_rankings"][0]["signal"] == "BUY"


def test_combined_cycle_fails_closed_for_incomplete_tcgcsv_map(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--product-map", str(_map(tmp_path / "map.csv", complete=False)),
            "--model-input", str(_model(tmp_path / "model.csv")),
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MTG_LIVE_EXECUTION": "false"},
    )
    assert result.returncode == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "INCOMPLETE"
    assert "TCGCSV_LANE_NOT_READY" in payload["reason_codes"]


def test_live_flag_is_blocked_without_environment_gate(tmp_path: Path) -> None:
    output = tmp_path / "latest.json"
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT), "--live",
            "--product-map", str(_map(tmp_path / "map.csv")),
            "--model-input", str(_model(tmp_path / "model.csv")),
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MTG_LIVE_EXECUTION": "false"},
    )
    assert result.returncode == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "SAFE_HOLD"
    assert payload["live_api_called"] is False
    assert "MTG_LIVE_EXECUTION_ENV_DISABLED" in payload["reason_codes"]
