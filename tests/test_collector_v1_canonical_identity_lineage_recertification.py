from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_canonical_identity_lineage_recertification_contract_v1.json"
LORWYN_CONTRACT = ROOT / "config/mtg/standards/collector_early_awareness_lorwyn_forecast_contract_v1.json"
SCRIPT = ROOT / "scripts/certify_collector_v1_canonical_identity_lineage.py"
PROHIBITED_KEYS = {"canonical_product_id", "tcgplayer_product_id", "investment_product_id"}


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_governance_package_exists_and_compiles() -> None:
    assert CONTRACT.is_file()
    assert LORWYN_CONTRACT.is_file()
    assert SCRIPT.is_file()
    py_compile.compile(str(SCRIPT), doraise=True)


def test_recertification_contract_has_exact_universe_controls() -> None:
    contract = load_contract()
    assert contract["required_governed_products"] == 50
    assert contract["required_base_forecast_products"] == 48
    assert contract["required_final_forecast_products"] == 49
    assert contract["required_horizons_days"] == [90, 180, 365, 730, 1095, 1825]
    assert contract["required_base_forecast_rows"] == 288
    assert contract["required_final_forecast_rows"] == 294
    assert contract["required_blocked_rows"] == 6
    assert contract["required_coverage_rows"] == 300
    assert contract["simulation_count"] == 10000


def test_recertification_uses_exact_certified_authority_paths() -> None:
    contract = load_contract()
    authorities = contract["authorities"]
    expected_supply = (
        "data/governance/permanence/certification/"
        "collector_v1_august1_current_data_package/"
        "collector_ebay_product_supply_snapshot.csv"
    )
    assert authorities["current_supply"] == expected_supply
    for relative in authorities.values():
        assert (ROOT / relative).is_file(), relative


def test_product_specific_lorwyn_contract_contains_no_identity_assertions() -> None:
    payload = json.loads(LORWYN_CONTRACT.read_text(encoding="utf-8"))
    lorwyn = payload["lorwyn"]
    assert lorwyn["requested_product_name"] == "Lorwyn Eclipsed - Collector Booster Display"
    assert lorwyn["identity_resolution_mode"] == "EXACT_NORMALIZED_NAME_SINGLE_AUTHORITY_ROW"
    assert PROHIBITED_KEYS.isdisjoint(lorwyn)


def test_repository_product_specific_model_contracts_reject_manual_identity_keys() -> None:
    contract = load_contract()
    violations: list[str] = []
    for pattern in contract["product_specific_contract_globs"]:
        for path in ROOT.glob(pattern):
            if path == CONTRACT or not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(payload)
            product_specific = (
                "requested_product_name" in text
                or "standalone" in path.name.lower()
                or "lorwyn" in path.name.lower()
            )
            if not product_specific:
                continue

            def walk(value: object, pointer: str = "$") -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in PROHIBITED_KEYS:
                            violations.append(f"{path.relative_to(ROOT)}:{pointer}.{key}")
                        walk(child, f"{pointer}.{key}")
                elif isinstance(value, list):
                    for index, child in enumerate(value):
                        walk(child, f"{pointer}[{index}]")

            walk(payload)
    assert violations == []


def test_script_requires_semantic_certification_before_simulation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    certification_index = text.index('"simulation_authorized": not semantic_failures')
    simulation_gate_index = text.index('if semantic_certification["simulation_authorized"]:')
    rng_index = text.index("np.random.default_rng", simulation_gate_index)
    assert certification_index < simulation_gate_index < rng_index


def test_script_has_no_hardcoded_tcgplayer_product_identity_literals() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    suspicious: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("MTG-CANON-TCGPLAYER-"):
                suspicious.append(value)
    assert suspicious == []


def test_script_invalidates_bad_outputs_and_builds_complete_lineage() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required_tokens = [
        "collector_invalidated_output_ledger.csv",
        "collector_50_product_identity_reconciliation.csv",
        "collector_base_48_forecast_identity_recertification.csv",
        "collector_early_awareness_identity_recertification.csv",
        "collector_lorwyn_pre_simulation_semantic_certification.json",
        "collector_authority_bound_lorwyn_forecasts.csv",
        "collector_final_authority_bound_49_product_forecasts.csv",
        "collector_final_forecast_source_identity_lineage_manifest.csv",
        "PRODUCT_SPECIFIC_CONTRACT_MANUAL_IDENTITY_ASSERTION",
        "BASE_FORECAST_IDENTITY_PRICE_METHOD_RECERTIFICATION_FAILED",
        "EARLY_AWARENESS_IDENTITY_RECERTIFICATION_FAILED",
        "LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION_FAILED",
        "FORECAST_LINEAGE_NOT_CLOSED",
    ]
    for token in required_tokens:
        assert token in text


def test_downstream_authorization_remains_false() -> None:
    contract = load_contract()
    governance = contract["governance"]
    assert governance["production_forecast_authorized"] is False
    assert governance["ranking_authorized"] is False
    assert governance["purchase_recommendations_authorized"] is False
