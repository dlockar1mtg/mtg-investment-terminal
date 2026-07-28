import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/operations/mtg_universal_market_valuation"


def test_builder_creates_1141_unique_rows():
    result = subprocess.run(
        [sys.executable, "scripts/build_universal_mtg_market_valuation.py"],
        cwd=ROOT,
    )
    assert result.returncode == 0

    with (OUTPUT / "universal_mtg_market_valuation.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1141
    assert len({row["canonical_product_id"] for row in rows}) == 1141
    assert all(
        row["model_eligible"] == "false"
        for row in rows
        if row["selected_source_type"] == "CURRENT_ASKING_REFERENCE"
    )

    summary = json.loads(
        (OUTPUT / "universal_mtg_market_valuation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["status"] == "PASS"
