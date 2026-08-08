from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_COUNT = 131
EXPECTED_IDENTITY = (
    "d540be20ff26709b8e004e18ff16a11a05f50a1182777dcfd86a1821f62b7ac2"
)


def fail(message: str) -> None:
    raise RuntimeError(
        f"FAIL-CLOSED: {message}"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--gate",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--tournament-design",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--final-gate",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--certified-input-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    gate = load_json(
        args.gate
    )

    design = load_json(
        args.tournament_design
    )

    final_gate = load_json(
        args.final_gate
    )

    binding = gate[
        "canonical_binding"
    ]

    if (
        binding["product_count"]
        != EXPECTED_COUNT
    ):
        fail(
            "diagnostic execution gate count mismatch"
        )

    if (
        binding["identity_sha256"]
        != EXPECTED_IDENTITY
    ):
        fail(
            "diagnostic execution gate identity mismatch"
        )

    if (
        design[
            "canonical_binding"
        ][
            "product_count"
        ]
        != EXPECTED_COUNT
    ):
        fail(
            "tournament design count mismatch"
        )

    if (
        design[
            "canonical_binding"
        ][
            "identity_sha256"
        ]
        != EXPECTED_IDENTITY
    ):
        fail(
            "tournament design identity mismatch"
        )

    if (
        final_gate[
            "canonical_target_authority"
        ][
            "canonical_product_count"
        ]
        != EXPECTED_COUNT
    ):
        fail(
            "final eligibility gate count mismatch"
        )

    if (
        final_gate[
            "canonical_target_authority"
        ][
            "canonical_universe_identity_sha256"
        ]
        != EXPECTED_IDENTITY
    ):
        fail(
            "final eligibility gate identity mismatch"
        )

    # ------------------------------------------------------------------------
    # Verify every package named by the execution gate
    # ------------------------------------------------------------------------

    verified_packages = []

    for name, spec in gate[
        "certified_input_packages"
    ].items():

        package_name = spec[
            "package_name"
        ]

        expected_sha = spec[
            "package_sha256"
        ]

        package_path = (
            args.certified_input_root
            / package_name
        )

        if not package_path.is_file():
            fail(
                f"missing certified package: {package_name}"
            )

        actual_sha = sha256_file(
            package_path
        )

        if actual_sha != expected_sha:
            fail(
                f"certified package SHA mismatch: {package_name}"
            )

        verified_packages.append(
            {
                "binding":
                    name,

                "package_name":
                    package_name,

                "sha256":
                    actual_sha,
            }
        )

    # ------------------------------------------------------------------------
    # Design must remain pre-execution
    # ------------------------------------------------------------------------

    design_auth = design[
        "execution_authorization"
    ]

    if (
        design_auth[
            "tournament_execution"
        ]
        is not False
    ):
        fail(
            "design contract was mutated to authorize execution"
        )

    if (
        design_auth[
            "model_execution"
        ]
        is not False
    ):
        fail(
            "design contract model execution flag drift"
        )

    # ------------------------------------------------------------------------
    # Final selection gate must remain incomplete
    # ------------------------------------------------------------------------

    final_inputs = final_gate[
        "required_pre_execution_inputs"
    ]

    for required_false in (
        "model_treatment_disposition_ledger",
        "exclusion_sensitivity_evidence",
        "owner_approval_for_persistent_exclusions",
    ):
        if (
            final_inputs[
                required_false
            ]
            is not False
        ):
            fail(
                "final model-selection gate unexpectedly satisfied "
                + required_false
            )

    final_auth = final_gate[
        "authorization"
    ]

    if (
        final_auth[
            "model_execution"
        ]
        is not False
    ):
        fail(
            "final model-selection execution became authorized"
        )

    if (
        final_auth[
            "forecast_execution"
        ]
        is not False
    ):
        fail(
            "forecast execution became authorized"
        )

    # ------------------------------------------------------------------------
    # Diagnostic gate authorization
    # ------------------------------------------------------------------------

    auth = gate[
        "authorization"
    ]

    required_true = (
        "diagnostic_tournament_execution",
        "diagnostic_model_fitting",
        "oos_diagnostic_execution",
        "influence_diagnostic_execution",
        "stability_diagnostic_execution",
        "exclusion_sensitivity_execution",
        "treatment_proposal_generation",
    )

    for name in required_true:
        if auth[name] is not True:
            fail(
                f"required diagnostic authorization false: {name}"
            )

    required_false = (
        "final_model_selection",
        "persistent_treatment_assignment",
        "persistent_exclusion",
        "production_model_execution",
        "forecast_execution",
        "monte_carlo_execution",
        "ranking_execution",
        "purchase_analysis",
        "purchase_recommendations",
    )

    for name in required_false:
        if auth[name] is not False:
            fail(
                f"prohibited downstream authorization true: {name}"
            )

    required_outputs = gate[
        "required_execution_outputs"
    ]

    if len(required_outputs) != 13:
        fail(
            "required tournament output count drift"
        )

    result = {
        "status":
            "PASS_PRECOLLECTOR_DIAGNOSTIC_TOURNAMENT_EXECUTION_GATE_V1",

        "canonical_product_count":
            EXPECTED_COUNT,

        "canonical_identity_sha256":
            EXPECTED_IDENTITY,

        "certified_packages_verified":
            len(verified_packages),

        "verified_packages":
            verified_packages,

        "required_execution_outputs":
            len(required_outputs),

        "diagnostic_tournament_execution_authorized":
            True,

        "diagnostic_model_fitting_authorized":
            True,

        "final_model_selection_authorized":
            False,

        "persistent_treatment_assignment_authorized":
            False,

        "persistent_exclusion_authorized":
            False,

        "production_model_execution_authorized":
            False,

        "forecast_execution_authorized":
            False,

        "ranking_execution_authorized":
            False,

        "purchase_analysis_authorized":
            False,

        "authorized_next_stage":
            "IMPLEMENT_AND_RUN_PRECOLLECTOR_DIAGNOSTIC_MODEL_TOURNAMENT",
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            result,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "PASS_PRECOLLECTOR_DIAGNOSTIC_TOURNAMENT_EXECUTION_GATE_V1"
    )

    print(
        "CANONICAL_PRODUCT_COUNT=131"
    )

    print(
        f"CERTIFIED_PACKAGES_VERIFIED={len(verified_packages)}"
    )

    print(
        f"REQUIRED_EXECUTION_OUTPUTS={len(required_outputs)}"
    )

    print(
        "DIAGNOSTIC_TOURNAMENT_EXECUTION_AUTHORIZED=TRUE"
    )

    print(
        "DIAGNOSTIC_MODEL_FITTING_AUTHORIZED=TRUE"
    )

    print(
        "FINAL_MODEL_SELECTION_AUTHORIZED=FALSE"
    )

    print(
        "PERSISTENT_TREATMENT_ASSIGNMENT_AUTHORIZED=FALSE"
    )

    print(
        "PERSISTENT_EXCLUSION_AUTHORIZED=FALSE"
    )

    print(
        "PRODUCTION_MODEL_EXECUTION_AUTHORIZED=FALSE"
    )

    print(
        "FORECAST_EXECUTION_AUTHORIZED=FALSE"
    )

    print(
        "RANKING_EXECUTION_AUTHORIZED=FALSE"
    )

    print(
        "PURCHASE_ANALYSIS_AUTHORIZED=FALSE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())