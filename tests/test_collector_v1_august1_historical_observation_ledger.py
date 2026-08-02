from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_august1_historical_observation_ledger_contract_v1.json"
SCRIPT = ROOT / "scripts/build_collector_v1_august1_historical_observation_ledger.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_is_bounded_to_august1_snapshot() -> None:
    payload = load_contract()
    assert payload["contract_name"] == "Collector August 1 Historical Observation Ledger"
    assert payload["governing_snapshot_id"] == "collector-20260801T211201Z-7688afbd"


def test_contract_requires_certified_row_level_input() -> None:
    cfg = load_contract()["row_level_certification"]
    assert cfg["required_status"] == "PASS_COLLECTOR_AUGUST1_ROW_LEVEL_RECONSTRUCTION_CERTIFICATION"
    assert cfg["candidate_history_sha256"] == "bd12f6707ee8bd4f45342df843c22c151296ff6afe36c2b4b2eddbc704dc15dd"
    assert cfg["required_rows"] == 1215
    assert cfg["required_products"] == 49
    assert cfg["required_dates"] == 30


def test_governed_no_history_exception_is_preserved() -> None:
    payload = load_contract()
    assert payload["required_governed_no_history_products"] == 1
    assert payload["required_exception_tcgplayer_product_id"] == "706142"


def test_downstream_controls_remain_fail_closed() -> None:
    auth = load_contract()["authorization"]
    assert auth["historical_observation_ledger_build_authorized"] is True
    assert auth["historical_observation_ledger_admission_authorized"] is True
    assert auth["historical_coverage_assessment_authorized_after_admission"] is True
    for key in [
        "lifecycle_panel_build_authorized",
        "model_tournament_authorized",
        "production_forecasting_authorized",
        "uip_delivery_authorized",
        "purchase_recommendations_authorized",
    ]:
        assert auth[key] is False


def test_script_contains_required_ledger_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    required = [
        "PASS_COLLECTOR_AUGUST1_HISTORICAL_OBSERVATION_LEDGER",
        "ROW_LEVEL_CERTIFICATION_STATUS_INVALID",
        "CANDIDATE_HISTORY_SHA256_MISMATCH",
        "DUPLICATE_LEDGER_PRODUCT_DATE_KEYS",
        "DUPLICATE_LEDGER_OBSERVATION_IDS",
        "ADMITTED_CERTIFIED_RECONSTRUCTION",
        '"historical_coverage_assessment_authorized": not failures',
        '"purchase_recommendations_authorized": False',
    ]
    assert all(token in text for token in required)


def test_ledger_ids_are_deterministic() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "snapshot_id|canonical_id|observation_date" not in text
    assert 'f"{snapshot_id}|{canonical_id}|{observation_date}"' in text
    assert "COLLECTOR-HIST-" in text
