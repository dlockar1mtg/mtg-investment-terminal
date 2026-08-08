from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_COUNT = 186
EXPECTED_IDENTITY = (
    "e75151ab05e87c60559e3114b050717307678f4ed0da01f067de46474a7ed4ac"
)

EXPECTED_ELIGIBILITY_CONTRACT = (
    "config/mtg/standards/"
    "precollector_model_eligibility_and_exclusion_contract_v1.json"
)


def fail(message: str) -> None:
    raise RuntimeError(f"FAIL-CLOSED: {message}")


def load_json(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_contract(contract: dict) -> None:
    target = contract["canonical_target_authority"]
    principles = contract["eligibility_principles"]
    history = contract["historical_model_selection"]
    auth = contract["authorization"]

    if target["canonical_product_count"] != EXPECTED_COUNT:
        fail("canonical product count mismatch")

    if target["canonical_universe_identity_sha256"] != EXPECTED_IDENTITY:
        fail("canonical universe identity mismatch")

    if target["sole_binding_target_authority"] is not True:
        fail("canonical universe is not sole target authority")

    if target["historical_target_authority_allowed"] is not False:
        fail("historical target authority remains allowed")

    if target["collector_target_authority_allowed"] is not False:
        fail("Collector target authority is allowed")

    if history["artifact_count"] != 17:
        fail("historical MODEL_SELECTION artifact count mismatch")

    if history["implementation_logic_reusable"] is not True:
        fail("historical implementation reuse was not preserved")

    if history["historical_execution_bindings_reusable"] is not False:
        fail("historical execution bindings remain reusable")

    if history["historical_snapshot_binding_authoritative"] is not False:
        fail("historical snapshot remains target authority")

    if history["historical_79_product_universe_authoritative"] is not False:
        fail("historical 79-product universe remains target authority")

    if contract["required_model_eligibility_standard"] != EXPECTED_ELIGIBILITY_CONTRACT:
        fail("wrong model-eligibility contract")

    for field in (
        "arbitrary_age_cutoffs_allowed",
        "arbitrary_release_year_cutoffs_allowed",
        "arbitrary_vintage_cutoffs_allowed",
        "exclusion_for_model_improvement_alone_allowed",
    ):
        if principles[field] is not False:
            fail(f"{field} must be false")

    if principles["canonical_products_begin_model_eligible"] is not True:
        fail("canonical products do not begin model eligible")

    if principles["empirical_diagnostics_required"] is not True:
        fail("empirical diagnostics are not required")

    if principles["model_specific_dispositions_required"] is not True:
        fail("model-specific dispositions are not required")

    if principles["persistent_exclusion_requires_owner_review"] is not True:
        fail("persistent exclusion owner review is not required")

    if principles["excluded_training_product_remains_canonical"] is not True:
        fail("training exclusion removes canonical identity")

    required_dimensions = {
        "PRICE_HISTORY_COVERAGE",
        "CURRENT_AVAILABILITY",
        "STATISTICAL_INFLUENCE",
        "OUT_OF_SAMPLE_ERROR_CONTRIBUTION",
        "MODEL_STABILITY",
        "EXCLUSION_SENSITIVITY",
    }

    actual_dimensions = set(contract["required_diagnostic_dimensions"])

    if not required_dimensions.issubset(actual_dimensions):
        fail("required empirical diagnostic dimensions are incomplete")

    if auth["model_execution"] is not False:
        fail("model execution was prematurely authorized")

    if auth["forecast_execution"] is not False:
        fail("forecast execution was prematurely authorized")

    if auth["monte_carlo_execution"] is not False:
        fail("Monte Carlo execution was prematurely authorized")

    if auth["ranking_execution"] is not False:
        fail("ranking execution was prematurely authorized")

    if auth["purchase_analysis"] is not False:
        fail("purchase analysis was prematurely authorized")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    args = parser.parse_args()

    contract = load_json(Path(args.contract))
    validate_contract(contract)

    print(
        "PASS_PRECOLLECTOR_MODEL_SELECTION_"
        "REBINDING_ELIGIBILITY_GATE"
    )
    print("CANONICAL_PRODUCT_COUNT=186")
    print("HISTORICAL_MODEL_ARTIFACTS=17")
    print("HISTORICAL_EXECUTION_BINDINGS_AUTHORIZED=FALSE")
    print("ARBITRARY_AGE_CUTOFF_ALLOWED=FALSE")
    print("ARBITRARY_RELEASE_YEAR_CUTOFF_ALLOWED=FALSE")
    print("ARBITRARY_VINTAGE_CUTOFF_ALLOWED=FALSE")
    print("EMPIRICAL_DIAGNOSTICS_REQUIRED=TRUE")
    print("PERSISTENT_EXCLUSION_REQUIRES_OWNER_REVIEW=TRUE")
    print("MODEL_EXECUTION_AUTHORIZED=FALSE")
    print(
        "NEXT_STAGE="
        "BUILD_PRECOLLECTOR_EMPIRICAL_MODEL_ELIGIBILITY_DIAGNOSTICS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())