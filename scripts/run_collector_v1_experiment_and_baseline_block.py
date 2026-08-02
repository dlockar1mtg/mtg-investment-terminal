from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> int:
    return int(subprocess.run(command, cwd=ROOT, check=False).returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build = [sys.executable, "scripts/build_collector_v1_scarcity_v1a_and_experiments.py"]
    backtest = [sys.executable, "scripts/run_collector_v1_routed_baseline_backtests.py"]
    if args.strict:
        build.append("--strict")
        backtest.append("--strict")

    rc = run(build)
    if rc != 0:
        print("Collector V1 experiment foundation failed; baseline backtests were not run.")
        return rc

    rc = run(backtest)
    if rc != 0:
        print("Collector V1 routed baseline backtests failed.")
        return rc

    print("PASS_COLLECTOR_V1_EXPERIMENT_AND_BASELINE_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
