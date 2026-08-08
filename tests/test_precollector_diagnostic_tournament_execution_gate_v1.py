import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

GATE = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_diagnostic_tournament_execution_gate_v1.json"
)

FINAL_GATE = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_model_selection_rebinding_and_eligibility_gate_contract_v2.json"
)


def load(path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def test_gate_exists():
    assert GATE.is_file()


def test_gate_bound_to_131():
    gate = load(GATE)

    assert (
        gate["canonical_binding"]["product_count"]
        == 131
    )


def test_diagnostic_execution_is_authorized():
    gate = load(GATE)

    auth = gate["authorization"]

    assert (
        auth["diagnostic_tournament_execution"]
        is True
    )

    assert (
        auth["diagnostic_model_fitting"]
        is True
    )

    assert (
        auth["oos_diagnostic_execution"]
        is True
    )

    assert (
        auth["influence_diagnostic_execution"]
        is True
    )

    assert (
        auth["stability_diagnostic_execution"]
        is True
    )

    assert (
        auth["exclusion_sensitivity_execution"]
        is True
    )


def test_persistent_decisions_remain_blocked():
    gate = load(GATE)

    auth = gate["authorization"]

    assert (
        auth["persistent_treatment_assignment"]
        is False
    )

    assert (
        auth["persistent_exclusion"]
        is False
    )

    assert (
        auth["final_model_selection"]
        is False
    )


def test_downstream_execution_remains_blocked():
    gate = load(GATE)

    auth = gate["authorization"]

    assert (
        auth["production_model_execution"]
        is False
    )

    assert auth["forecast_execution"] is False
    assert auth["monte_carlo_execution"] is False
    assert auth["ranking_execution"] is False
    assert auth["purchase_analysis"] is False
    assert auth["purchase_recommendations"] is False


def test_final_selection_gate_remains_incomplete():
    final_gate = load(FINAL_GATE)

    inputs = final_gate[
        "required_pre_execution_inputs"
    ]

    assert (
        inputs[
            "model_treatment_disposition_ledger"
        ]
        is False
    )

    assert (
        inputs[
            "exclusion_sensitivity_evidence"
        ]
        is False
    )

    assert (
        inputs[
            "owner_approval_for_persistent_exclusions"
        ]
        is False
    )

    auth = final_gate[
        "authorization"
    ]

    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False


def test_no_training_population_is_preselected():
    gate = load(GATE)

    population = gate[
        "population_governance"
    ]

    assert (
        population[
            "training_population_preselected"
        ]
        is False
    )

    assert (
        population[
            "products_pre_excluded"
        ]
        == 0
    )

    assert (
        population[
            "products_pre_downweighted"
        ]
        == 0
    )


def test_no_arbitrary_cutoffs():
    gate = load(GATE)

    population = gate[
        "population_governance"
    ]

    assert population["age_cutoff_allowed"] is False
    assert population["release_year_cutoff_allowed"] is False
    assert population["fixed_listing_threshold_allowed"] is False
    assert population["fixed_seller_threshold_allowed"] is False


def test_all_required_outputs_are_locked():
    gate = load(GATE)

    assert len(
        gate[
            "required_execution_outputs"
        ]
    ) == 13


def test_final_gate_not_superseded():
    gate = load(GATE)

    relationship = gate[
        "final_gate_relationship"
    ]

    assert (
        relationship[
            "final_gate_is_superseded_by_this_gate"
        ]
        is False
    )

    assert (
        relationship[
            "final_gate_product_disposition_requirement_remains"
        ]
        is True
    )

    assert (
        relationship[
            "final_gate_exclusion_sensitivity_requirement_remains"
        ]
        is True
    )

    assert (
        relationship[
            "final_gate_owner_review_requirement_remains"
        ]
        is True
    )