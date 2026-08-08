import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_historical_price_authority_v2_contract.json"
)


def load_contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8-sig"))


def test_contract_exists():
    assert CONTRACT.is_file()


def test_contract_uses_stage9_186_product_universe():
    contract = load_contract()
    universe = contract["canonical_universe"]

    assert universe["product_count"] == 186
    assert (
        universe["identity_sha256"]
        == "e75151ab05e87c60559e3114b050717307678f4ed0da01f067de46474a7ed4ac"
    )


def test_direct_tcgcsv_is_only_admitted_history_source():
    contract = load_contract()
    source = contract["admitted_historical_source"]

    assert source["source_class"] == "TCGCSV_ARCHIVE_MONTHLY_DIRECT"
    assert source["direct_source_only"] is True
    assert source["universal_combined_ledger_authorized"] is False
    assert source["ebay_history_authorized"] is False


def test_expected_certification_counts():
    contract = load_contract()
    expected = contract["expected_certification_result"]

    assert expected["canonical_product_count"] == 186
    assert expected["admitted_product_count"] == 115
    assert expected["historical_gap_product_count"] == 71
    assert expected["admitted_observation_count"] == 3390
    assert expected["distinct_observation_date_count"] == 30
    assert expected["duplicate_product_date_conflict_count"] == 0


def test_history_gaps_do_not_change_canonical_or_model_status():
    contract = load_contract()
    policy = contract["historical_gap_policy"]

    assert policy["gap_products_remain_canonical"] is True
    assert policy["gap_products_automatically_excluded_from_models"] is False
    assert policy["synthetic_case_price_derivation_allowed"] is False
    assert policy["base_box_history_may_be_used_as_case_price"] is False


def test_downstream_execution_remains_disabled():
    contract = load_contract()
    auth = contract["authorization"]

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["monte_carlo_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False
    assert auth["purchase_recommendations"] is False