from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str) -> None:
    command = [sys.executable, *arguments]
    print("\n> " + " ".join(command))
    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )


def main() -> int:
    run(
        "scripts/build_phase_8_2_1d_2_secret_lair_historical_performance.py"
    )
    run(
        "scripts/certify_phase_8_2_1d_2_historical_forecast_separation.py"
    )
    print("\nPHASE 8.2.1D.2 REBUILD CHAIN: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
