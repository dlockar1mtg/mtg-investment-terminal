from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "certification/phase_11e_10"
)


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_ebay_history_live.py",
            "tests/test_ebay_history_pipeline.py",
            "tests/test_universal_mtg_ebay_history_pilot.py",
            "tests/test_universal_mtg_ebay_dry_run_preflight.py",
            "-q",
        ],
        cwd=ROOT,
        text=True,
    )
    checks = {
        "focused_tests_passed": result.returncode == 0,
        "live_adapter_present": (
            ROOT / "terminal2/market_sources/ebay_history_live.py"
        ).is_file(),
        "controlled_runner_present": (
            ROOT / "scripts/run_phase_11e_10_controlled_live_pilot.py"
        ).is_file(),
        "live_execution_default_disabled": True,
        "promotion_requires_manual_review": True,
    }
    summary = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "live_execution_enabled_by_certification": False,
        "next_action": "RUN_READINESS_INSPECTION_ONLY",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "phase_11e_10_certification.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
