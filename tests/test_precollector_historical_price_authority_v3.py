import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_historical_price_authority_v3_contract.json"
)


def load_contract():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_authority_targets_corrected_131_universe():
    contract = load_contract()

    assert (
        contract["canonical_universe"]["product_count"]
        == 131
    )

    assert (
        contract["canonical_universe"]["identity_sha256"]
        == "d540be20ff26709b8e004e18ff16a11a05f50a1182777dcfd86a1821f62b7ac2"
    )


def test_history_is_rebound_not_recollected():
    contract = load_contract()
    source = contract["source_historical_authority"]

    assert source["source_recollection_required"] is False
    assert source["filtering_to_corrected_universe_required"] is True


def test_cases_cannot_be_normalized_into_box_history():
    contract = load_contract()
    excluded = contract["excluded_commercial_units"]

    assert excluded["multi_box_cases"] is True
    assert excluded["case_history_may_be_transformed_to_box_history"] is False
    assert excluded["case_price_division_allowed"] is False


def test_missing_history_does_not_auto_exclude_model():
    contract = load_contract()
    gaps = contract["gap_policy"]

    assert gaps["products_without_history_remain_canonical"] is True
    assert gaps["absence_of_history_automatically_excludes_model"] is False


def test_model_execution_stays_disabled():
    contract = load_contract()
    auth = contract["authorization"]

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False