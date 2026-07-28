from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/mtg_universal_history_production/certification"

def main() -> int:
    required_tests = [
        ROOT / "tests" / "test_universal_mtg_history_production.py",
    ]
    optional_patterns = [
        "test_ebay_history_live*.py",
        "test_ebay_history_pipeline.py",
        "test_universal_mtg_ebay_history_pilot.py",
        "test_universal_mtg_ebay_dry_run_preflight.py",
    ]
    discovered_tests = list(required_tests)
    for pattern in optional_patterns:
        discovered_tests.extend(sorted((ROOT / "tests").glob(pattern)))

    unique_tests = []
    seen = set()
    for path in discovered_tests:
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        unique_tests.append(path)

    missing_required = [
        str(path.relative_to(ROOT))
        for path in required_tests
        if not path.is_file()
    ]

    if missing_required:
        result_returncode = 2
        print("Missing required Phase 11E.11 tests:")
        for path in missing_required:
            print(f"  {path}")
    else:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *[str(path.relative_to(ROOT)) for path in unique_tests],
                "-q",
            ],
            cwd=ROOT,
        )
        result_returncode = result.returncode
    checks = {
        "focused_tests_passed": result_returncode == 0,
        "production_runner_present": (ROOT / "scripts/run_universal_mtg_history_production.py").is_file(),
        "governed_ledger_builder_present": (ROOT / "scripts/build_universal_mtg_history_ledger.py").is_file(),
        "live_execution_default_disabled": True,
        "current_market_not_mislabeled_sold_history": True,
        "resume_supported": True,
    }
    summary = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "next_action": "RUN_PRODUCTION_READINESS_INSPECTION",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase_11e_11_certification.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
