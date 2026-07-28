import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/mtg_governed_consumption_integration"


def test_builder_creates_governed_universal_interface():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_phase_11e_14_consumption_integration.py",
        ],
        cwd=ROOT,
    )
    assert result.returncode == 0

    with (OUT / "universal_mtg_consumption_interface.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1141
    assert len({row["canonical_product_id"] for row in rows}) == 1141
    assert all(
        row["governed_forecast_eligible"] == "false"
        for row in rows
        if row["valuation_state"] == "CURRENT_ASKING_REFERENCE_ONLY"
    )

    summary = json.loads(
        (OUT / "universal_mtg_consumption_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["status"] == "PASS"
