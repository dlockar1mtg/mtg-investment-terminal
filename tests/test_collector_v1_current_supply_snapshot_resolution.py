from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/mtg/standards/collector_current_supply_snapshot_resolution_contract_v1.json"
SCRIPT = ROOT / "scripts/resolve_collector_v1_current_supply_snapshot.py"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_and_script_exist() -> None:
    assert CONTRACT.is_file()
    assert SCRIPT.is_file()


def test_snapshot_identity_is_frozen() -> None:
    contract = load_contract()
    assert contract["snapshot_id"] == "collector-20260801T211201Z-7688afbd"
    assert contract["snapshot_date"] == "2026-08-01"
    assert contract["required_product_rows"] == 50


def test_search_is_bounded() -> None:
    contract = load_contract()
    assert contract["governance"]["bounded_search_only"] is True
    assert contract["bounded_search_roots"] == [
        "data/governance/permanence/certification",
        "data/operations/mtg_universal_history_completion",
    ]


def test_canonical_output_path_matches_production_builder() -> None:
    contract = load_contract()
    assert contract["canonical_output_path"] == (
        "data/governance/permanence/certification/"
        "collector_v1_august1_current_data_package/"
        "collector_ebay_product_supply_snapshot.csv"
    )


def test_identity_and_overlay_thresholds_are_governed() -> None:
    contract = load_contract()
    assert contract["minimum_identity_coverage"] >= 0.98
    assert contract["minimum_overlay_feature_coverage"] >= 0.80
    assert "canonical_product_id" in contract["required_identity_aliases"]
    assert len(contract["overlay_feature_alias_groups"]) == 4


def test_source_is_preserved_and_copy_is_exact() -> None:
    governance = load_contract()["governance"]
    assert governance["source_file_must_not_be_modified"] is True
    assert governance["canonical_copy_must_preserve_rows"] is True
    assert governance["exactly_one_source_must_be_selected"] is True


def test_overlay_cannot_change_forecast_or_backtest() -> None:
    governance = load_contract()["governance"]
    assert governance["current_supply_demand_post_forecast_only"] is True
    assert governance["historical_backtest_use_allowed"] is False
    assert governance["point_forecast_rewrite_allowed"] is False
    assert governance["purchase_recommendations_authorized"] is False


def test_script_contains_fail_closed_controls() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "NO_VALID_50_PRODUCT_SUPPLY_SNAPSHOT_FOUND" in source
    assert "AMBIGUOUS_TOP_SUPPLY_SNAPSHOT_CANDIDATES" in source
    assert "CANONICAL_COPY_HASH_MISMATCH" in source
    assert "rglob(\"*.csv\")" in source
    assert "shutil.copyfile" in source
