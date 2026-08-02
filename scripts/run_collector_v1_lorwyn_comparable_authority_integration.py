from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "phase-8.2.8a-august1-snapshot-bound-current-product-rebuild"
OUTPUT = ROOT / "data/governance/permanence/certification/collector_v1_lorwyn_comparable_authority_integration"
SUMMARY = OUTPUT / "collector_lorwyn_comparable_authority_integration_summary.json"
AUTHORITY = OUTPUT / "collector_integrated_comparable_pool_authority.csv"
AUDIT = OUTPUT / "collector_lorwyn_supplemental_comparable_integration_audit.csv"


def run(args: list[str]) -> int:
    return subprocess.run(args, cwd=ROOT, check=False).returncode


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fail(message: str, code: int) -> int:
    print("\nCOLLECTOR GOVERNANCE EXECUTION BLOCKED")
    print(message)
    print("No semantic simulation, ranking, or purchasing was authorized.")
    return code


def main() -> int:
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, text=True, capture_output=True, check=False)
    if branch.returncode or branch.stdout.strip() != EXPECTED_BRANCH:
        return fail("Unexpected branch.", 1)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    if status.returncode or status.stdout.strip():
        return fail("Working tree is not clean.", 2)

    focused = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_collector_v1_lorwyn_comparable_authority_integration.py",
        "tests/test_collector_v1_lorwyn_target_specific_comparables.py",
        "tests/test_collector_v1_canonical_identity_lineage_v2.py",
        "tests/test_collector_v1_canonical_identity_lineage_python_runner.py",
        "-q",
    ]
    if run(focused):
        return fail("Focused governance tests failed.", 3)

    if run([sys.executable, "scripts/integrate_collector_v1_lorwyn_comparable_authority.py"]):
        return fail("Comparable-authority integration engine failed.", 4)

    for path in [SUMMARY, AUTHORITY, AUDIT]:
        if not path.is_file():
            return fail(f"Missing output: {path.relative_to(ROOT)}", 5)

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    authority_rows = read_csv(AUTHORITY)
    audit_rows = read_csv(AUDIT)
    pairs = {(row["target_canonical_product_id"], row["comparable_canonical_product_id"]) for row in authority_rows}
    targets = {row["target_canonical_product_id"] for row in authority_rows}
    failed_audit = [row for row in audit_rows if row.get("identity_release_semantic_reconciled") != "True"]

    checks = {
        "status": summary.get("status") == "PASS_COLLECTOR_LORWYN_COMPARABLE_AUTHORITY_INTEGRATION",
        "original_rows": summary.get("original_rows") == 115,
        "supplemental_rows": summary.get("supplemental_rows") == 6,
        "integrated_rows": summary.get("integrated_rows") == 121 and len(authority_rows) == 121,
        "target_count": summary.get("integrated_targets") == 24 and len(targets) == 24,
        "unique_pairs": summary.get("integrated_unique_pairs") == 121 and len(pairs) == 121,
        "original_hash_unchanged": summary.get("original_authority_sha256_before") == summary.get("original_authority_sha256_after"),
        "audit_rows": len(audit_rows) == 6 and not failed_audit,
        "critical_failures": not summary.get("critical_failures"),
        "authorization_blocks": all(summary.get(key) is False for key in ["projection_authorized", "production_forecast_authorized", "ranking_authorized", "purchase_recommendations_authorized"]),
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        return fail("Integration verification failed: " + ", ".join(failed), 6)

    collector_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_collector_v1*.py"))
    if run([sys.executable, "-m", "pytest", *collector_tests, "-q"]):
        return fail("Complete Collector regression failed.", 7)

    final_status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False)
    if final_status.returncode or final_status.stdout.strip():
        return fail("Working tree is not clean after integration.", 8)

    print("\nPASS_COLLECTOR_LORWYN_COMPARABLE_AUTHORITY_INTEGRATION")
    print("Integrated authority: 121 rows, 24 targets, 121 unique pairs.")
    print("Original comparable authority remained byte-identical.")
    print("Ranking status: BLOCKED")
    print("Purchase status: BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
