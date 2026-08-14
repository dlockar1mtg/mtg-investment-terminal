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


def test_hosted_delivery_builds_from_certified_phase9_authority(tmp_path):
    module = load_module()
    result = module.build(tmp_path)

    assert result["status"] == "PASS"
    assert result["products"] == 968
    assert result["delivery_contract"] == "uip-mtg-delivery-v2"
    assert result["generic_surfaces_are_semantic_authority"] is False
    assert result["snapshot_population_is_permanent"] is False
    assert result["automatic_purchase_execution"] is False
    assert result["execution_ready_purchase_certified"] is False

    latest = tmp_path / "latest"
    required = {
        "asset_master.csv",
        "forecasts.csv",
        "recommendations.csv",
        "risk_metrics.csv",
        "portfolio_positions.csv",
        "platform_status.csv",
        "diagnostics.csv",
        "mtg_native_authority.csv",
        "mtg_native_authority_manifest.json",
        "export_manifest.json",
        "package_summary.json",
    }
    assert required.issubset({path.name for path in latest.iterdir()})
    assert len(read_rows(latest / "asset_master.csv")) == 968
    assert len(read_rows(latest / "mtg_native_authority.csv")) == 968
    assert read_rows(latest / "diagnostics.csv") == []


def test_delivery_uses_dynamic_certified_lane_counts(tmp_path):
    module = load_module()
    module.build(tmp_path)
    manifest = json.loads(
        (tmp_path / "latest" / "package_summary.json").read_text(encoding="utf-8")
    )

    assert manifest["lane_counts"] == {
        "COLLECTOR_V1": 50,
        "PRE_COLLECTOR_V1": 131,
        "SECRET_LAIR_V1_1": 787,
    }
    assert manifest["products"] == sum(manifest["lane_counts"].values())
    assert manifest["snapshot_population_is_permanent"] is False


def test_semantic_authority_is_byte_preserved(tmp_path):
    module = load_module()
    result = module.build(tmp_path)
    latest = tmp_path / "latest"

    source_bytes = module.CERTIFIED_PAYLOAD.read_bytes()
    delivered_bytes = (latest / "mtg_native_authority.csv").read_bytes()

    assert delivered_bytes == source_bytes
    assert result["semantic_authority_sha256"] == module.sha256(module.CERTIFIED_PAYLOAD)


def test_no_legacy_fixed_phase8_history_dependency():
    module = load_module()
    assert not hasattr(module, "HISTORICAL_PERFORMANCE_SOURCE")
    assert not hasattr(module, "EXPECTED_COUNTS")
