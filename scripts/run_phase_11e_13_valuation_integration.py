from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS = [
    [sys.executable, "scripts/build_universal_mtg_history_ledger.py"],
    [sys.executable, "scripts/build_mtg_current_market_accumulation.py"],
    [sys.executable, "scripts/build_universal_mtg_market_valuation.py"],
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
