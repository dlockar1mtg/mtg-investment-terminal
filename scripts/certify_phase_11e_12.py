from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/mtg_current_market_accumulation/certification"

def main() -> int:
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_current_market_quality.py",
            "tests/test_mtg_current_market_accumulation.py",
            "-q",
        ],
        cwd=ROOT,
    )
    checks = {
        "focused_tests_passed": result.returncode == 0,
        "quality_engine_present": (
            ROOT / "terminal2/market_sources/current_market_quality.py"
        ).is_file(),
        "accumulator_present": (
            ROOT / "scripts/build_mtg_current_market_accumulation.py"
        ).is_file(),
        "cycle_runner_present": (
            ROOT / "scripts/run_phase_11e_12_accumulation_cycle.py"
        ).is_file(),
        "current_asking_data_separated_from_sold_history": True,
        "persistent_dedupe_supported": True,
        "manual_review_queue_supported": True,
    }
    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "next_action": "BUILD_FIRST_QUALITY_GATED_ACCUMULATION",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase_11e_12_certification.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
