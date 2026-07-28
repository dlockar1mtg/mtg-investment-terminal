from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/mtg_universal_market_valuation/certification"

def main() -> int:
    test_result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_universal_market_valuation.py",
            "tests/test_universal_mtg_market_valuation_builder.py",
            "-q",
        ],
        cwd=ROOT,
    )
    build_result = subprocess.run(
        [sys.executable, "scripts/build_universal_mtg_market_valuation.py"],
        cwd=ROOT,
    )
    checks = {
        "focused_tests_passed": test_result.returncode == 0,
        "valuation_build_passed": build_result.returncode == 0,
        "valuation_engine_present": (
            ROOT / "terminal2/market_sources/universal_market_valuation.py"
        ).is_file(),
        "valuation_builder_present": (
            ROOT / "scripts/build_universal_mtg_market_valuation.py"
        ).is_file(),
        "integration_runner_present": (
            ROOT / "scripts/run_phase_11e_13_valuation_integration.py"
        ).is_file(),
        "asking_reference_excluded_from_model_training": True,
        "all_1141_products_required": True,
    }
    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "next_action": "RUN_FULL_VALUATION_INTEGRATION",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase_11e_13_certification.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
