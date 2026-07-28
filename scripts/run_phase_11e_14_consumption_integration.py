from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS = [
    [sys.executable, "scripts/run_phase_11e_13_valuation_integration.py"],
    [sys.executable, "scripts/build_phase_11e_14_consumption_integration.py"],
]

def main() -> int:
    for command in COMMANDS:
        print("\n>", " ".join(command))
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
