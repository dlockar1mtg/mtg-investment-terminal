from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/precollector_tournament_certified_input_bundle_drift_gate_contract_v1.json"
BUILDER = ROOT / "scripts/audit_precollector_tournament_certified_input_bundle_drift.py"


def data() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_binds_known_certified_packages() -> None:
    packages = data()["required_certified_packages"]
    assert len(packages) == 3
    assert all(len(item["sha256"]) == 64 for item in packages)


def test_contract_preserves_expected_counts() -> None:
    counts = data()["expected_counts"]
    assert counts == {
        "active_products": 79,
        "excluded_products": 15,
        "forecast_horizons": 5,
        "product_horizon_rows": 395,
        "forecast_routes": 3,
        "approved_comparable_rows": 369,
    }


def test_contract_requires_canonical_history_and_tournament_inputs() -> None:
    roles = set(data()["required_artifact_roles"])
    assert "CANONICAL_HISTORICAL_PRICE" in roles
    assert "ACTIVE_PRODUCT_UNIVERSE" in roles
    assert "PRODUCT_HORIZON_MATRIX" in roles
    assert "HORIZON_ARCHITECTURE" in roles
    assert "ROUTE_MODEL_ELIGIBILITY" in roles


def test_contract_prohibits_recursive_rebuild_and_network_collection() -> None:
    prohibited = data()["prohibited_behavior"]
    assert prohibited["delete_upstream_artifacts"] is True
    assert prohibited["invoke_upstream_builders"] is True
    assert prohibited["perform_live_network_collection"] is True
    assert prohibited["repair_drift_automatically"] is True


def test_contract_keeps_all_downstream_authority_false() -> None:
    contract = data()
    for key in [
        "forecast_generation_authorized", "ranking_execution_authorized",
        "purchase_analysis_authorized", "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized", "uip_delivery_authorized",
    ]:
        assert contract[key] is False


def test_builder_contains_no_subprocess_or_upstream_deletion() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "shutil.rmtree" not in text
    assert "urlopen" not in text
    assert "requests." not in text


def test_builder_hash_binds_packages_and_fails_closed() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "CERTIFIED_PACKAGE_HASH_DRIFT" in text
    assert "CERTIFIED_PACKAGE_MISSING" in text
    assert "CERTIFIED_ARTIFACT_ROLE_MISSING" in text
    assert "return 0 if status == \"PASS\" else 2" in text


def test_builder_module_loads() -> None:
    spec = importlib.util.spec_from_file_location("precollector_certified_input_drift", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
