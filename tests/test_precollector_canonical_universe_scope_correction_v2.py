import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "precollector_canonical_universe_scope_correction_v2.json"
)


def load_contract():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_corrected_target_count_is_131():
    contract = load_contract()
    scope = contract["corrected_scope"]

    assert scope["expected_corrected_product_count"] == 131
    assert scope["expected_removed_case_count"] == 55
    assert scope["expected_unresolved_product_form_count"] == 0


def test_cases_are_not_target_products():
    contract = load_contract()
    scope = contract["corrected_scope"]

    assert scope["exclude_booster_box_case"] is True
    assert scope["exclude_sealed_case"] is True
    assert scope["exclude_master_case"] is True
    assert scope["exclude_case_of_multiple_boxes"] is True


def test_case_removal_is_not_model_exclusion():
    contract = load_contract()
    policy = contract["removal_policy"]

    assert policy["removal_is_model_exclusion"] is False
    assert policy["removal_is_statistical_exclusion"] is False
    assert policy["removal_is_age_based"] is False


def test_case_price_normalization_is_prohibited():
    contract = load_contract()
    policy = contract["removal_policy"]

    assert policy["case_to_box_price_division_allowed"] is False
    assert policy["synthetic_case_normalization_allowed"] is False


def test_old_downstream_bindings_require_rework():
    contract = load_contract()
    downstream = contract["downstream_rebinding"]

    assert downstream["historical_source_recollection_required"] is False
    assert downstream["historical_authority_filter_and_rebind_required"] is True
    assert downstream["fresh_current_price_rerun_required"] is True
    assert downstream["fresh_ebay_rerun_required"] is True
    assert downstream["ebay_high_recall_page_limit"] == 200
    assert downstream["ebay_cases_must_be_rejected"] is True


def test_model_execution_remains_disabled():
    contract = load_contract()
    auth = contract["authorization"]

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False