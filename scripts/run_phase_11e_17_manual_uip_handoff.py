from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS = [
    [sys.executable, "scripts/run_phase_11e_15_production_delivery.py"],
    [sys.executable, "scripts/build_phase_11e_17_uip_handoff.py"],
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
