import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_current_price_authority_v2_contract.json"
)


def load_contract():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_current_authority_is_bound_to_131():
    contract = load_contract()

    assert (
        contract["canonical_universe"]["product_count"]
        == 131
    )


def test_expected_fresh_coverage():
    contract = load_contract()
    source = contract["source"]

    assert source["source_product_count"] == 121
    assert source["explicit_gap_product_count"] == 10
    assert source["group_request_failures"] == 0


def test_tcgcsv_is_direct_current_price_source():
    contract = load_contract()
    source = contract["source"]

    assert source["source_name"] == "TCGCSV_LIVE"
    assert source["direct_tcgplayer_identity_required"] is True
    assert source["ebay_used_as_current_price_source"] is False


def test_synthetic_price_prohibited():
    contract = load_contract()
    selection = contract["price_selection"]

    assert selection["synthetic_price_allowed"] is False
    assert selection["case_price_conversion_allowed"] is False


def test_current_price_gap_does_not_auto_exclude():
    contract = load_contract()
    gaps = contract["gap_policy"]

    assert (
        gaps["missing_current_price_implies_model_exclusion"]
        is False
    )

    assert (
        gaps["missing_current_price_implies_prediction_exclusion"]
        is False
    )


def test_execution_remains_disabled():
    contract = load_contract()
    auth = contract["authorization"]

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False