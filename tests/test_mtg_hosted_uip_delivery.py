from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_mtg_hosted_uip_delivery.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_mtg_hosted_uip_delivery", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_hosted_delivery_builds_complete_contract(tmp_path):
    module = load_module()
    result = module.build(tmp_path)
    assert result["status"] == "PASS"
    assert result["products"] == 1141
    latest = tmp_path / "latest"
    required = {
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_positions.csv",
        "platform_status.csv",
        "diagnostics.csv",
        "export_manifest.json",
        "package_summary.json",
    }
    assert required.issubset({path.name for path in latest.iterdir()})
    assert len(read_rows(latest / "asset_master.csv")) == 1141
    assert read_rows(latest / "diagnostics.csv") == []


def test_delivery_manifest_has_expected_lanes(tmp_path):
    module = load_module()
    module.build(tmp_path)
    manifest = json.loads((tmp_path / "latest" / "package_summary.json").read_text())
    assert manifest["lane_counts"] == {
        "SECRET_LAIR": 973,
        "COLLECTOR_BOOSTER_BOX": 49,
        "PRE_COLLECTOR_BOOSTER_BOX": 119,
    }
