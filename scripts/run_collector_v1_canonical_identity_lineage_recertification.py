from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "phase-8.2.8a-august1-snapshot-bound-current-product-rebuild"
CONTRACT = ROOT / "config/mtg/standards/collector_canonical_identity_lineage_recertification_contract_v1.json"
CERTIFIER = ROOT / "scripts/certify_collector_v1_canonical_identity_lineage_v2.py"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_canonical_identity_lineage_recertification"
SUMMARY = OUTPUT / "collector_canonical_identity_lineage_recertification_summary.json"
FINAL_FORECASTS = OUTPUT / "collector_final_authority_bound_49_product_forecasts.csv"
BLOCKED = OUTPUT / "collector_final_authority_bound_blocked_horizons.csv"
LINEAGE = OUTPUT / "collector_final_forecast_source_identity_lineage_manifest.csv"
BASE_AUDIT = OUTPUT / "collector_base_48_forecast_identity_recertification.csv"
EARLY_AUDIT = OUTPUT / "collector_early_awareness_identity_recertification.csv"
LORWYN = OUTPUT / "collector_authority_bound_lorwyn_forecasts.csv"
SEMANTIC = OUTPUT / "collector_lorwyn_pre_simulation_semantic_certification.json"


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=capture, check=False)
    if capture:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
    return completed


def fail(message: str, code: int = 1) -> int:
    print("\n============================================================")
    print("COLLECTOR GOVERNANCE EXECUTION BLOCKED")
    print("============================================================")
    print(message)
    print("No calibration was authorized.")
    print("No ranking was authorized.")
    print("No purchase recommendation was authorized.")
    return code


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    print("\n============================================================")
    print("COLLECTOR PROJECT STATUS")
    print("============================================================")
    print("COMPLETED / CERTIFIED")
    print("1. Product-specific contracts no longer assert identity.")
    print("2. Certified authority is the exclusive identity source.")
    print("3. Authority schemas are explicitly preflighted.")
    print("\nCURRENTLY WORKING ON")
    print("4. Reconcile all 50 governed products.")
    print("5. Recertify 288 base forecast rows.")
    print("6. Recertify early-awareness identity lineage.")
    print("7. Invalidate incorrect derived outputs.")
    print("8. Rebuild Lorwyn after semantic certification.")
    print("9. Close lineage for all 294 final forecasts.")
    print("\nSTILL OUTSTANDING")
    print("10. Probabilistic calibration.")
    print("11. Final rankings.")
    print("12. Product analysis and purchase authorization.")

    branch = run(["git", "branch", "--show-current"], capture=True)
    if branch.returncode != 0 or branch.stdout.strip() != EXPECTED_BRANCH:
        return fail(f"Expected branch {EXPECTED_BRANCH}.", 901)
    status = run(["git", "status", "--porcelain"], capture=True)
    if status.returncode != 0 or status.stdout.strip():
        return fail("Working tree is not clean.", 902)

    if not CONTRACT.is_file() or not CERTIFIER.is_file():
        return fail("Governance contract or v2 certifier is missing.", 903)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    missing_authorities = [
        f"{name}:{relative}"
        for name, relative in contract["authorities"].items()
        if not (ROOT / relative).is_file()
    ]
    if missing_authorities:
        return fail("Missing declared authorities: " + "; ".join(missing_authorities), 904)
    print("PASS: Every declared authority exists.")

    focused_tests = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_collector_v1_authority_schema_preflight.py",
        "tests/test_collector_v1_canonical_identity_lineage_v2.py",
        "tests/test_collector_v1_canonical_identity_lineage_recertification.py",
        "tests/test_collector_v1_early_awareness_lorwyn_forecast.py",
        "tests/test_collector_v1_complete_horizon_probabilistic_forecasts.py",
        "tests/test_collector_v1_final_model_output_validation.py",
        "-q",
    ]
    if run(focused_tests).returncode != 0:
        return fail("Governance-focused tests failed.", 905)

    certification = run([sys.executable, str(CERTIFIER.relative_to(ROOT))])
    if certification.returncode != 0:
        return fail("Canonical identity and lineage recertification failed.", certification.returncode or 906)

    required = [SUMMARY, FINAL_FORECASTS, BLOCKED, LINEAGE, BASE_AUDIT, EARLY_AUDIT, LORWYN, SEMANTIC]
    missing_outputs = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing_outputs:
        return fail("Missing required outputs: " + "; ".join(missing_outputs), 907)

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    final_rows = read_csv(FINAL_FORECASTS)
    blocked_rows = read_csv(BLOCKED)
    lineage_rows = read_csv(LINEAGE)
    base_rows = read_csv(BASE_AUDIT)
    early_rows = read_csv(EARLY_AUDIT)
    lorwyn_rows = read_csv(LORWYN)
    semantic = json.loads(SEMANTIC.read_text(encoding="utf-8"))

    unique_keys = {(row["canonical_product_id"], row["horizon_days"]) for row in final_rows}
    unique_products = {row["canonical_product_id"] for row in final_rows}
    checks = {
        "status": summary.get("status") == "PASS_COLLECTOR_CANONICAL_IDENTITY_LINEAGE_RECERTIFICATION",
        "governed_products": summary.get("governed_products") == 50,
        "products_reconciled": summary.get("products_reconciled") == 50,
        "manual_identity_assertions": summary.get("manual_identity_assertion_violations") == 0,
        "unknown_identities": summary.get("unknown_identity_rows") == 0,
        "name_identity_mismatches": summary.get("name_identity_mismatches") == 0,
        "base_rows": summary.get("base_forecast_rows_recertified") == 288 and all(row.get("recertified") == "True" for row in base_rows),
        "early_awareness": summary.get("early_awareness_rows_audited") == summary.get("early_awareness_rows_recertified") and all(row.get("identity_reconciled") == "True" for row in early_rows),
        "lorwyn_semantic": semantic.get("status") == "PASS_LORWYN_PRE_SIMULATION_SEMANTIC_CERTIFICATION" and semantic.get("simulation_authorized") is True,
        "lorwyn_rows": len(lorwyn_rows) == 6,
        "final_universe": len(final_rows) == 294 and len(unique_keys) == 294 and len(unique_products) == 49,
        "blocked_rows": len(blocked_rows) == 6,
        "coverage": summary.get("coverage_rows") == 300,
        "lineage": len(lineage_rows) == 294 and all(row.get("lineage_closed") == "True" for row in lineage_rows),
        "critical_failures": not summary.get("critical_failures"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    if failed:
        return fail("Final recertification checks failed: " + ", ".join(failed), 908)

    collector_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_collector_v1*.py"))
    if run([sys.executable, "-m", "pytest", *collector_tests, "-q"]).returncode != 0:
        return fail("Complete Collector regression suite failed.", 909)

    final_status = run(["git", "status", "--porcelain"], capture=True)
    if final_status.returncode != 0 or final_status.stdout.strip():
        return fail("Repository is not clean after recertification.", 910)

    print("\n============================================================")
    print("COLLECTOR PROJECT STATUS AFTER EXECUTION")
    print("============================================================")
    print("COMPLETED / CERTIFIED")
    print("1. All 50 governed products reconciled.")
    print("2. All 288 base forecast rows recertified.")
    print("3. All early-awareness identities recertified.")
    print("4. Incorrect derived outputs invalidated.")
    print("5. Lorwyn rebuilt only after semantic certification.")
    print("6. Final 49-product forecast authority created.")
    print("7. All 294 final forecasts have closed lineage.")
    print("\nCURRENTLY WORKING ON")
    print("8. Probabilistic calibration and reasonableness review.")
    print("\nSTILL OUTSTANDING")
    print("9. Final rankings.")
    print("10. Product analysis and purchase authorization.")
    print("\nOVERALL RESULT: CANONICAL IDENTITY AND LINEAGE RECERTIFIED")
    print("RANKING STATUS: BLOCKED")
    print("PURCHASE STATUS: BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
