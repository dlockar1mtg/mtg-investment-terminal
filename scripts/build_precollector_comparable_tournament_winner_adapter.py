from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "scripts/build_precollector_comparable_model_tournament_calibration.py"
TOURNAMENT_DIR = ROOT / "artifacts/precollector/comparable_model_tournament_calibration"
SUMMARY_PATH = TOURNAMENT_DIR / "precollector_comparable_model_tournament_calibration_summary.json"
OUTPUT_PATH = TOURNAMENT_DIR / "precollector_comparable_model_tournament_winner.csv"


def main() -> int:
    completed = subprocess.run([sys.executable, str(UPSTREAM)], cwd=ROOT, check=False)
    if completed.returncode != 0:
        return int(completed.returncode)
    if not SUMMARY_PATH.is_file():
        raise RuntimeError("TOURNAMENT_SUMMARY_MISSING")
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    if summary.get("certification_status") != "PASS":
        raise RuntimeError("TOURNAMENT_NOT_CERTIFIED")
    model_name = str(summary.get("selected_model", "")).strip()
    if not model_name:
        raise RuntimeError("TOURNAMENT_WINNER_MISSING")
    frame = pd.DataFrame([{
        "model_name": model_name,
        "winner_median_absolute_log_error": summary.get("winner_median_absolute_log_error"),
        "winner_p90_absolute_log_error": summary.get("winner_p90_absolute_log_error"),
        "winner_required_target_coverage": summary.get("winner_required_target_coverage"),
        "certification_status": summary.get("certification_status"),
        "forecast_generation_authorized": False,
    }])
    frame.to_csv(OUTPUT_PATH, index=False)
    print("PASS_PRECOLLECTOR_COMPARABLE_TOURNAMENT_WINNER_ADAPTER")
    print(f"SELECTED_MODEL={model_name}")
    print("FORECAST_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
