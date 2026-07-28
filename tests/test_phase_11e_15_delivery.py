import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_certification_delivery_package(tmp_path: Path):
    delivery = tmp_path / "mtg_terminal_delivery"
    package_id = "phase-11e-15-test"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/publish_phase_11e_15_terminal_delivery.py",
            "--output-root",
            str(delivery),
            "--package-id",
            package_id,
        ],
        cwd=ROOT,
    )
    assert result.returncode == 0

    manifest = json.loads(
        (delivery / "latest/delivery_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "PASS"
    assert manifest["package_id"] == package_id
    assert manifest["current_asking_is_sold_history"] is False
    assert manifest["current_asking_model_eligible"] is False

    with (
        delivery / "latest/universal_mtg_consumption_interface.csv"
    ).open("r", encoding="utf-8-sig", newline="") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 1141
