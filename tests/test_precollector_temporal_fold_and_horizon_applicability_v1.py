import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_temporal_fold_and_horizon_applicability_v1.json"
)


def load():
    return json.loads(
        CONTRACT.read_text(
            encoding="utf-8-sig"
        )
    )


def test_contract_exists():
    assert CONTRACT.is_file()


def test_bound_to_131_products():
    contract = load()

    assert (
        contract[
            "canonical_binding"
        ][
            "product_count"
        ]
        == 131
    )


def test_all_governed_horizons_are_present():
    contract = load()

    assert (
        contract[
            "governed_horizons_days"
        ]
        == [
            90,
            180,
            365,
            1095,
            1825,
        ]
    )


def test_realized_endpoint_is_on_or_after_target():
    contract = load()

    folds = contract[
        "fold_construction"
    ]

    assert (
        folds[
            "realized_endpoint_rule"
        ]
        == "FIRST_CERTIFIED_PRODUCT_OBSERVATION_ON_OR_AFTER_TARGET_DATE"
    )


def test_no_arbitrary_endpoint_tolerance():
    contract = load()

    folds = contract[
        "fold_construction"
    ]

    assert (
        folds[
            "endpoint_tolerance_imposed"
        ]
        is False
    )

    assert (
        folds[
            "endpoint_tolerance_days"
        ]
        is None
    )


def test_unsupported_horizon_does_not_exclude_product():
    contract = load()

    applicability = contract[
        "applicability_governance"
    ]

    assert (
        applicability[
            "zero_realized_folds_is_canonical_exclusion"
        ]
        is False
    )

    assert (
        applicability[
            "zero_realized_folds_is_model_exclusion"
        ]
        is False
    )

    assert (
        applicability[
            "zero_realized_folds_is_prediction_exclusion"
        ]
        is False
    )


def test_no_model_execution_in_fold_stage():
    contract = load()

    auth = contract[
        "authorization"
    ]

    assert auth["model_fitting"] is False
    assert auth["treatment_assignment"] is False
    assert auth["persistent_exclusion"] is False
    assert auth["production_forecast"] is False
    assert auth["ranking"] is False
    assert auth["purchase_analysis"] is False