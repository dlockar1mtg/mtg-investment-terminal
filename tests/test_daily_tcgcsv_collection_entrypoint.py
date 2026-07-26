from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_daily_tcgcsv_collection.py"


def _run(product_map: Path, summary: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
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


def test_tcgcsv_wrapper_dry_run_does_not_call_live_source(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text(
        "box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\nExample,1,3,10\n",
        encoding="utf-8",
    )
    summary = tmp_path / "summary.json"

    result = _run(product_map, summary)

    assert result.returncode == 0
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "DRY_RUN"
    assert payload["live_api_called"] is False
    assert payload["product_map_available"] is True
    assert payload["product_map_rows"] == 1
    assert payload["complete_mapping_rows"] == 1


def test_tcgcsv_wrapper_fails_closed_without_product_map(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    result = _run(tmp_path / "missing.csv", summary)

    assert result.returncode == 1
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert payload["live_api_called"] is False
    assert "TCGCSV_PRODUCT_MAP_NOT_AVAILABLE" in payload["reason_codes"]


def test_tcgcsv_wrapper_fails_closed_when_group_ids_are_missing(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text(
        "box_name,tcgplayer_product_id,tcgcsv_category_id,tcgcsv_group_id\nExample,1,3,\n",
        encoding="utf-8",
    )
    summary = tmp_path / "summary.json"

    result = _run(product_map, summary)

    assert result.returncode == 2
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "INCOMPLETE"
    assert payload["product_map_rows"] == 1
    assert payload["complete_mapping_rows"] == 0
    assert payload["reason_codes"] == ["TCGCSV_NO_COMPLETE_PRODUCT_MAPPINGS"]


def test_tcgcsv_wrapper_rejects_invalid_schema(tmp_path: Path) -> None:
    product_map = tmp_path / "product_map.csv"
    product_map.write_text("box_name,tcgplayer_product_id\nExample,1\n", encoding="utf-8")
    summary = tmp_path / "summary.json"

    result = _run(product_map, summary)

    assert result.returncode == 1
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "tcgcsv_group_id" in payload["missing_required_columns"]
    assert payload["reason_codes"] == ["TCGCSV_PRODUCT_MAP_SCHEMA_INVALID"]
