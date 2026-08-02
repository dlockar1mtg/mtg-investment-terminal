from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_early_awareness_lorwyn_forecast_contract_v1.json"
CURRENT = ROOT / "data/governance/permanence/certification/collector_v1_final_premodel_user_exclusion_resolution/collector_final_current_price_authority.csv"
BASE_FORECAST = ROOT / "data/governance/permanence/certification/collector_v1_complete_horizon_probabilistic_forecast/collector_complete_horizon_probabilistic_forecasts.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_lorwyn_contract_uses_authoritative_identity() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["lorwyn"]["canonical_product_id"] == "MTG-CANON-TCGPLAYER-656322"
    assert contract["lorwyn"]["tcgplayer_product_id"] == "656322"


def test_lorwyn_identity_matches_current_authority_by_id_and_name() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rows = read_csv(CURRENT)
    matches = [
        row
        for row in rows
        if row.get("canonical_product_id", "").strip()
        == contract["lorwyn"]["canonical_product_id"]
    ]
    assert len(matches) == 1
    assert "lorwyn eclipsed" in matches[0].get("product_name", "").lower()
    assert matches[0].get("tcgplayer_product_id", "").strip() == "656322"


def test_lorwyn_identity_does_not_collide_with_base_forecast_universe() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rows = read_csv(BASE_FORECAST)
    base_ids = {
        row.get("canonical_product_id", "").strip()
        for row in rows
        if row.get("canonical_product_id", "").strip()
    }
    assert contract["lorwyn"]["canonical_product_id"] not in base_ids


def test_prior_incorrect_identity_is_not_lorwyn() -> None:
    rows = read_csv(CURRENT)
    prior_matches = [
        row
        for row in rows
        if row.get("canonical_product_id", "").strip()
        == "MTG-CANON-TCGPLAYER-648650"
    ]
    assert len(prior_matches) == 1
    assert "lorwyn eclipsed" not in prior_matches[0].get("product_name", "").lower()
