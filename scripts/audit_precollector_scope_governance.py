from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "config/mtg/governance/mtg_github_first_governed_execution_workflow_v1.json"
SCOPE = ROOT / "config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json"
STANDARD = ROOT / "docs/standards/mtg/MTG_FORECASTING_STANDARD.md"
BASELINE = ROOT / "docs/phase_8/precollector/PRECOLLECTOR_BOOSTER_SCOPE_AND_IDENTITY_BASELINE.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict:
    require(path.is_file(), f"Missing required file: {path.relative_to(ROOT)}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    workflow = load_json(WORKFLOW)
    scope = load_json(SCOPE)
    require(STANDARD.is_file(), "Canonical MTG forecasting standard is missing")
    require(BASELINE.is_file(), "Precollector scope baseline is missing")

    controls = workflow["mandatory_controls"]
    required_true = [
        "github_first_changes",
        "single_copy_run_powershell_entrypoint",
        "targeted_governance_tests_required",
        "mtg_standard_conformance_tests_required",
        "relevant_regression_tests_required",
        "full_suite_required_before_certification_or_merge",
        "fail_closed_on_any_error",
        "phase_advancement_requires_all_gates_pass",
        "forecast_ranking_purchase_separation_required",
    ]
    for key in required_true:
        require(controls.get(key) is True, f"Workflow control weakened: {key}")
    require(controls.get("automatic_execution_default") is False, "Automatic execution must remain disabled")
    require(controls.get("standards_drift_tolerance") == "ZERO", "Standards drift tolerance must be ZERO")

    governance = scope["governance_controls"]
    for key in (
        "forecast_generation_authorized",
        "ranking_execution_authorized",
        "purchase_recommendation_authorized",
        "automatic_purchase_execution_authorized",
    ):
        require(governance.get(key) is False, f"Unauthorized downstream authority enabled: {key}")

    basis = scope["scope_basis"]
    require(basis.get("calendar_cutoff_used") is False, "Scope must not use a calendar cutoff")
    required_exclusions = {
        "Collector Booster boxes",
        "Draft Booster boxes",
        "Play Booster boxes",
        "foreign-language booster boxes",
        "loose booster packs",
        "damaged-seal boxes",
    }
    actual_exclusions = set(scope.get("excluded_product_families", []))
    require(required_exclusions.issubset(actual_exclusions), "Required product exclusions are incomplete")

    standard_text = STANDARD.read_text(encoding="utf-8")
    for clause in (
        "Required horizons are one, three, and five years.",
        "Required scenarios are downside, base, and upside.",
        "Forecast generation and purchase authorization remain separate.",
    ):
        require(clause in standard_text, f"Canonical MTG standard clause missing: {clause}")

    baseline_text = BASELINE.read_text(encoding="utf-8")
    require("Forecast generation: **not authorized**" in baseline_text, "Baseline forecast authorization drift")
    require("Ranking execution: **not authorized**" in baseline_text, "Baseline ranking authorization drift")
    require("Purchase recommendation generation: **not authorized**" in baseline_text, "Baseline purchase authorization drift")

    print("PASS_PRECOLLECTOR_SCOPE_GOVERNANCE")
    print("PASS_MTG_STANDARD_CONFORMANCE")
    print("PASS_GITHUB_FIRST_WORKFLOW_CONTROL")
    print("NEXT_STAGE_AUTHORIZED=CANDIDATE_UNIVERSE_INVENTORY_ONLY")


if __name__ == "__main__":
    main()
