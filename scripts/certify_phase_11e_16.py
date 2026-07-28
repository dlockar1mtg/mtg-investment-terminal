from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/operations/mtg_terminal_activation"
ACTIVE = ROOT / "data/warehouse/current/governed_terminal"


def main() -> int:
    tests = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_governed_loader.py",
            "tests/test_phase_11e_16_terminal_activation.py",
            "-q",
        ],
        cwd=ROOT,
    )
    activation = subprocess.run(
        [sys.executable, "scripts/activate_phase_11e_16_terminal.py"],
        cwd=ROOT,
    )
    status_path = STATE / "terminal_activation_status.json"
    status = (
        json.loads(status_path.read_text(encoding="utf-8"))
        if status_path.is_file() else {}
    )
    checks = {
        "focused_tests_passed": tests.returncode == 0,
        "activation_passed": activation.returncode == 0,
        "activation_status_present": status_path.is_file(),
        "activation_status_pass": status.get("status") == "PASS",
        "interface_rows_equal_1141": status.get("interface_rows") == 1141,
        "active_dashboard_present": (ACTIVE / "dashboard.csv").is_file(),
        "active_forecasts_present": (ACTIVE / "forecasts.csv").is_file(),
        "active_recommendations_present": (
            ACTIVE / "recommendations.csv"
        ).is_file(),
        "active_rankings_present": (ACTIVE / "rankings.csv").is_file(),
        "current_asking_not_sold_history": (
            status.get("current_asking_is_sold_history") is False
        ),
        "current_asking_not_model_eligible": (
            status.get("current_asking_model_eligible") is False
        ),
    }
    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "active_package_id": status.get("package_id", ""),
        "next_action": "RUN_FULL_TERMINAL_CUTOVER",
    }
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "phase_11e_16_certification.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
