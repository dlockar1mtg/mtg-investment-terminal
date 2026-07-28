from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    command = [sys.executable, *args]
    print("\n> " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run("scripts/recover_phase_8_2_1d_3_secret_lair_history.py")
    run("scripts/validate_phase_8_2_1d_3_no_loss_history.py")
    print("\nPHASE 8.2.1D.3 RECOVERY AND VALIDATION CHAIN: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
