from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, strict: bool) -> int:
    command = [sys.executable, str(ROOT / "scripts" / script)]
    if strict:
        command.append("--strict")
    completed = subprocess.run(command, cwd=ROOT)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build_code = run("rebuild_collector_v1_final_long_horizon_scenario_authority.py", args.strict)
    if build_code != 0:
        print("Final long-horizon scenario authority rebuild failed; certification was not run.")
        return build_code

    certify_code = run("certify_collector_v1_final_long_horizon_scenario_authority.py", args.strict)
    if certify_code != 0:
        print("Final long-horizon scenario authority certification failed.")
        return certify_code

    print("PASS_COLLECTOR_V1_FINAL_LONG_HORIZON_SCENARIO_AUTHORITY_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
