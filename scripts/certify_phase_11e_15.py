from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "data/operations/mtg_terminal_delivery"
CERT = DELIVERY / "certification"


def count_csv(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    test_result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_governed_publisher.py",
            "tests/test_phase_11e_15_delivery.py",
            "-q",
        ],
        cwd=ROOT,
    )
    publish_result = subprocess.run(
        [
            sys.executable,
            "scripts/publish_phase_11e_15_terminal_delivery.py",
            "--package-id",
            "phase-11e-15-certification",
        ],
        cwd=ROOT,
    )

    latest = DELIVERY / "latest"
    manifest_path = latest / "delivery_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file() else {}
    )

    checks = {
        "focused_tests_passed": test_result.returncode == 0,
        "certification_publish_passed": publish_result.returncode == 0,
        "latest_manifest_present": manifest_path.is_file(),
        "manifest_status_pass": manifest.get("status") == "PASS",
        "interface_rows_equal_1141": (
            (latest / "universal_mtg_consumption_interface.csv").is_file()
            and count_csv(
                latest / "universal_mtg_consumption_interface.csv"
            ) == 1141
        ),
        "current_asking_not_sold_history": (
            manifest.get("current_asking_is_sold_history") is False
        ),
        "current_asking_not_model_eligible": (
            manifest.get("current_asking_model_eligible") is False
        ),
        "required_delivery_files_present": all(
            (latest / name).is_file()
            for name in (
                "dashboard.csv",
                "forecasts.csv",
                "recommendations.csv",
                "rankings.csv",
                "exclusions.csv",
                "market_provenance.csv",
                "consumption_summary.json",
                "valuation_summary.json",
            )
        ),
    }

    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "certification_checks": checks,
        "latest_package_id": manifest.get("package_id", ""),
        "next_action": "RUN_PRODUCTION_DELIVERY",
    }
    CERT.mkdir(parents=True, exist_ok=True)
    (CERT / "phase_11e_15_certification.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
