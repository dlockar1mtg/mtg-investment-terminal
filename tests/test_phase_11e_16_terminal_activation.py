import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "data/warehouse/current/governed_terminal"
STATE = ROOT / "data/operations/mtg_terminal_activation"


def test_repository_delivery_activates():
    result = subprocess.run(
        [sys.executable, "scripts/activate_phase_11e_16_terminal.py"],
        cwd=ROOT,
    )
    assert result.returncode == 0
    status = json.loads(
        (STATE / "terminal_activation_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["status"] == "PASS"
    assert status["interface_rows"] == 1141
    assert status["current_asking_is_sold_history"] is False
    assert status["current_asking_model_eligible"] is False
    assert (ACTIVE / "dashboard.csv").is_file()
    assert (ACTIVE / "forecasts.csv").is_file()
    assert (ACTIVE / "recommendations.csv").is_file()
    assert (ACTIVE / "rankings.csv").is_file()
