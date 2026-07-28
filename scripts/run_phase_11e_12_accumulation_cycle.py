from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(command: list[str]) -> None:
    print("\n>", " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect-live", action="store_true")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()

    if args.collect_live:
        run([
            sys.executable,
            "scripts/run_universal_mtg_history_production.py",
            "--execute",
            "--confirmation",
            args.confirmation,
        ])

    run([
        sys.executable,
        "scripts/build_mtg_current_market_accumulation.py",
    ])
    run([
        sys.executable,
        "scripts/build_universal_mtg_history_ledger.py",
    ])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
