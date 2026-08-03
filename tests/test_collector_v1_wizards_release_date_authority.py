from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_wizards_release_date_authority_contract_v1.json"
EVIDENCE = ROOT / "data/governance/mtg/standards/collector_wizards_release_date_evidence_v1.csv"
SCRIPT = ROOT / "scripts/certify_collector_v1_wizards_release_date_authority.py"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_contract_and_script_exist() -> None:
    assert CONTRACT.is_file()
    assert EVIDENCE.is_file()
    assert SCRIPT.is_file()


def test_contract_preserves_fail_closed_downstream_controls() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    policy = contract["authorization_policy"]
    assert contract["required_product_count"] == 50
    assert contract["required_missing_evidence_rows"] == 27
    assert contract["required_ledger_rows"] == 1215
    assert policy["model_tournament_authorized"] is False
    assert policy["production_forecasting_authorized"] is False
    assert policy["uip_delivery_authorized"] is False
    assert policy["purchase_recommendations_authorized"] is False


def test_evidence_has_exactly_27_unique_governed_products() -> None:
    rows = read_csv(EVIDENCE)
    assert len(rows) == 27
    ids = [row["canonical_product_id"] for row in rows]
    tcg_ids = [row["tcgplayer_product_id"] for row in rows]
    assert len(ids) == len(set(ids)) == 27
    assert len(tcg_ids) == len(set(tcg_ids)) == 27


def test_all_evidence_uses_official_wizards_domain_and_iso_dates() -> None:
    rows = read_csv(EVIDENCE)
    for row in rows:
        assert urlparse(row["wizards_source_url"]).hostname == "magic.wizards.com"
        assert len(row["official_release_date"]) == 10
        assert row["official_release_date"][4] == "-"
        assert row["official_release_date"][7] == "-"
        assert row["evidence_status"] == "OFFICIAL_WIZARDS_EVIDENCE"
        assert row["evidence_statement"].strip()


def test_ikoria_uses_north_america_physical_release() -> None:
    rows = {row["tcgplayer_product_id"]: row for row in read_csv(EVIDENCE)}
    ikoria = rows["208279"]
    assert ikoria["official_release_date"] == "2020-05-15"
    assert ikoria["geographic_scope"] == "North America"
    assert ikoria["release_date_type"] == "PHYSICAL_TABLETOP_RELEASE"
