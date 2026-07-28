import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "data/operations/mtg_uip_handoff"


def test_repository_handoff_builds_without_dashboard_activation():
    result = subprocess.run(
        [sys.executable, "scripts/build_phase_11e_17_uip_handoff.py"],
        cwd=ROOT,
    )
    assert result.returncode == 0

    payload = json.loads(
        (HANDOFF / "latest_mtg_uip_handoff.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "READY_FOR_UIP_IMPORT"
    assert payload["governed_product_count"] == 1141
    assert payload["ownership"]["universal_investment_platform"]
    assert "dashboard publication and refresh" in payload[
        "ownership"
    ]["universal_investment_platform"]
