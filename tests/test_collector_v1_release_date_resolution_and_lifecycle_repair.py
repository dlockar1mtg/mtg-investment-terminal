from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_release_date_resolution_and_lifecycle_repair_contract_v1.json"
SCRIPT = ROOT / "scripts/repair_collector_v1_release_date_resolution_and_lifecycle.py"


def test_contract_exists_and_is_fail_closed() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["required_product_count"] == 50
    assert payload["required_ledger_rows"] == 1215
    assert payload["governance_rules"]["no_invented_release_dates"] is True
    assert payload["governance_rules"]["every_ledger_row_requires_classification"] is True
    assert payload["governance_rules"]["unresolved_release_dates_fail_closed"] is True
    assert payload["governance_rules"]["model_tournament_authorized"] is False
    assert payload["governance_rules"]["purchase_recommendations_authorized"] is False


def test_source_precedence_is_explicit() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    precedence = payload["release_date_source_precedence"]
    assert precedence[0] == "foundation.identity__raw_released_on"
    assert "premodel.release_date" in precedence


def test_lifecycle_bands_are_complete() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert set(payload["lifecycle_bands"]) == {
        "PRESALE", "RELEASE_MONTH", "EARLY_POST_RELEASE", "DEVELOPING", "ESTABLISHED"
    }


def test_script_preserves_governance_controls() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "resolve_release_date" in text
    assert "RELEASE_DATE_UNRESOLVED" in text
    assert "UNCLASSIFIED_LIFECYCLE_ROWS" in text
    assert "CANDIDATE_NOT_YET_AUTHORIZED" in text
    assert '"model_tournament_authorized": False' in text
    assert '"purchase_recommendations_authorized": False' in text


def test_failures_are_product_level_not_row_level() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "affected_rows=" in text
    assert "ledger_counts" in text
