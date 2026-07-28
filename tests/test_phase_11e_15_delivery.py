import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "data/operations/mtg_terminal_delivery"


def test_certification_delivery_package():
    package_id = "phase-11e-15-test"
    package = DELIVERY / "packages" / package_id
    if package.exists():
        import shutil
        shutil.rmtree(package)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/publish_phase_11e_15_terminal_delivery.py",
            "--package-id",
            package_id,
        ],
        cwd=ROOT,
    )
    assert result.returncode == 0

    manifest = json.loads(
        (DELIVERY / "latest/delivery_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "PASS"
    assert manifest["current_asking_is_sold_history"] is False
    assert manifest["current_asking_model_eligible"] is False

    with (
        DELIVERY / "latest/universal_mtg_consumption_interface.csv"
    ).open("r", encoding="utf-8-sig", newline="") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 1141
