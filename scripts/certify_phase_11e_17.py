from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "data/operations/mtg_uip_handoff"
DOCS = ROOT / "docs/phase_11e"


def main() -> int:
    focused = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_uip_handoff.py",
            "tests/test_phase_11e_17_manual_handoff.py",
            "-q",
        ],
        cwd=ROOT,
    )
    build = subprocess.run(
        [sys.executable, "scripts/build_phase_11e_17_uip_handoff.py"],
        cwd=ROOT,
    )

    handoff_path = HANDOFF / "latest_mtg_uip_handoff.json"
    handoff = (
        json.loads(handoff_path.read_text(encoding="utf-8"))
        if handoff_path.is_file()
        else {}
    )
    terminal_runner = (
        ROOT / "terminal2_run_all.py"
    ).read_text(encoding="utf-8")

    retired_paths = (
        ROOT / "scripts/activate_phase_11e_16_terminal.py",
        ROOT / "scripts/run_phase_11e_16_terminal_cutover.py",
        ROOT / "terminal2/delivery/governed_loader.py",
        ROOT / "tests/test_governed_loader.py",
        ROOT / "tests/test_phase_11e_16_terminal_activation.py",
    )

    checks = {
        "focused_tests_passed": focused.returncode == 0,
        "handoff_build_passed": build.returncode == 0,
        "handoff_status_ready": (
            handoff.get("status") == "READY_FOR_UIP_IMPORT"
        ),
        "handoff_contract_v1": (
            handoff.get("handoff_contract")
            == "mtg-to-uip-manual-production-v1"
        ),
        "package_id_present": bool(handoff.get("package_id")),
        "interface_rows_equal_1141": (
            handoff.get("row_counts", {}).get(
                "universal_mtg_consumption_interface.csv"
            )
            == 1141
        ),
        "current_asking_not_sold_history": (
            handoff.get("current_asking_is_sold_history") is False
        ),
        "current_asking_not_model_eligible": (
            handoff.get("current_asking_model_eligible") is False
        ),
        "local_activation_removed_from_terminal_runner": (
            "governed_loader" not in terminal_runner
            and "Governed terminal activation:" not in terminal_runner
        ),
        "local_activation_files_retired": all(
            not path.exists() for path in retired_paths
        ),
        "uip_owns_dashboard": (
            "dashboard publication and refresh"
            in handoff.get("ownership", {}).get(
                "universal_investment_platform", []
            )
        ),
        "uip_owns_refresh_scheduling": (
            "refresh scheduling"
            in handoff.get("ownership", {}).get(
                "universal_investment_platform", []
            )
        ),
    }

    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "package_id": handoff.get("package_id", ""),
        "manual_production_command": handoff.get(
            "manual_production_command", ""
        ),
        "next_repository": (
            r"C:\Users\DevonLockard\InvestmentPlatform"
        ),
        "next_action": "BUILD_UIP_MANUAL_MTG_IMPORT",
    }
    HANDOFF.mkdir(parents=True, exist_ok=True)
    cert_path = HANDOFF / "phase_11e_17_certification.json"
    cert_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "PHASE_11E_17_FINAL_CERTIFICATION.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
