from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_daily_tcgcsv_collection.py"


def test_tcgcsv_wrapper_dry_run_does_not_call_live_source(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text("box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\nExample,1,3,10\n", encoding="utf-8")
    summary = tmp_path / "summary.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--product-map",
            str(product_map),
            "--summary-output",
            str(summary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "DRY_RUN"
    assert payload["live_api_called"] is False
    assert payload["product_map_available"] is True


def test_tcgcsv_wrapper_fails_closed_without_product_map(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--product-map",
            str(tmp_path / "missing.csv"),
            "--summary-output",
            str(summary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert payload["live_api_called"] is False
    assert "TCGCSV_PRODUCT_MAP_NOT_AVAILABLE" in payload["reason_codes"]
