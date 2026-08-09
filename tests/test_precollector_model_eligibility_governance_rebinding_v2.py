import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

OWNER = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "precollector_model_eligibility_owner_decision_v2.json"
)

ELIGIBILITY = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_model_eligibility_and_exclusion_contract_v2.json"
)

GATE = (
    ROOT
    / "config"
    / "mtg"
    / "standards"
    / "precollector_model_selection_rebinding_and_eligibility_gate_contract_v2.json"
)


EXPECTED_SHA = (
    "d540be20ff26709b8e004e18ff16a11a05f50a1182777dcfd86a1821f62b7ac2"
)


def load(path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def test_v2_governance_files_exist():
    assert OWNER.is_file()
    assert ELIGIBILITY.is_file()
    assert GATE.is_file()


def test_every_v2_authority_is_bound_to_131():
    owner = load(OWNER)
    eligibility = load(ELIGIBILITY)
    gate = load(GATE)

    assert (
        owner[
            "canonical_universe_boundary"
        ][
            "canonical_product_count"
        ]
        == 131
    )

    assert (
        eligibility[
            "canonical_product_count"
        ]
        == 131
    )

    assert (
        gate[
            "canonical_target_authority"
        ][
            "canonical_product_count"
        ]
        == 131
    )


def test_every_v2_identity_binding_matches():
    owner = load(OWNER)
    eligibility = load(ELIGIBILITY)
    gate = load(GATE)

    assert (
        owner[
            "canonical_universe_boundary"
        ][
            "canonical_universe_identity_sha256"
        ]
        == EXPECTED_SHA
    )

    assert (
        eligibility[
            "canonical_universe_identity_sha256"
        ]
        == EXPECTED_SHA
    )

    assert (
        gate[
            "canonical_target_authority"
        ][
            "canonical_universe_identity_sha256"
        ]
        == EXPECTED_SHA
    )


def test_prior_186_binding_is_explicitly_superseded():
    owner = load(OWNER)
    gate = load(GATE)

    assert (
        owner[
            "prior_binding"
        ][
            "canonical_product_count"
        ]
        == 186
    )

    assert (
        owner[
            "prior_binding"
        ][
            "status"
        ]
        == "SUPERSEDED_BY_CERTIFIED_PRODUCT_FORM_SCOPE_CORRECTION"
    )

    assert (
        gate[
            "canonical_target_authority"
        ][
            "prior_186_product_authority_allowed"
        ]
        is False
    )


def test_empirical_anti_cherry_picking_rules_preserved():
    owner = load(OWNER)
    eligibility = load(ELIGIBILITY)

    assert (
        owner[
            "governing_principles"
        ][
            "arbitrary_age_cutoffs_allowed"
        ]
        is False
    )

    assert (
        owner[
            "required_exclusion_controls"
        ][
            "single_metric_improvement_is_sufficient"
        ]
        is False
    )

    assert (
        eligibility[
            "prohibited_shortcuts"
        ][
            "exclude_only_because_removal_improves_selected_metric"
        ]
        is True
    )

    assert (
        eligibility[
            "decision_rules"
        ][
            "persistent_exclusion_requires_owner_review"
        ]
        is True
    )


def test_partial_evidence_is_not_automatic_exclusion():
    owner = load(OWNER)

    assert (
        owner[
            "required_exclusion_controls"
        ][
            "missing_one_evidence_domain_alone_is_sufficient"
        ]
        is False
    )

    assert (
        owner[
            "certified_evidence_state"
        ][
            "products_currently_excluded"
        ]
        == 0
    )


def test_six_model_dependent_diagnostics_state_is_consistent():
    gate = load(GATE)

    completed = set(
        gate[
            "evidence_diagnostics_completed"
        ]
    )

    pending = set(
        gate[
            "model_dependent_diagnostics_pending"
        ]
    )

    assert completed == {
        "PRICE_HISTORY_COVERAGE",
        "PRICE_HISTORY_STALENESS",
        "PRICE_PATH_STABILITY",
        "CURRENT_AVAILABILITY",
        "LIQUIDITY_OR_MARKET_DEPTH",
        "SOURCE_DISAGREEMENT",
    }

    assert pending == {
        "STATISTICAL_INFLUENCE",
        "OUT_OF_SAMPLE_ERROR_CONTRIBUTION",
        "MODEL_STABILITY",
        "EXCLUSION_SENSITIVITY",
    }


def test_tournament_design_authorized_but_execution_not_authorized():
    gate = load(GATE)
    auth = gate["authorization"]

    assert auth["tournament_design"] is True
    assert auth["tournament_execution"] is False
    assert auth["model_execution"] is False
    assert auth["forecast_execution"] is False
    assert auth["ranking_execution"] is False


def test_model_execution_gate_is_still_incomplete():
    gate = load(GATE)

    inputs = gate[
        "required_pre_execution_inputs"
    ]

    assert (
        inputs[
            "governed_tournament_design"
        ]
        is False
    )

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