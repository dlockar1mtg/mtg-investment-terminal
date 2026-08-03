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

    build_code = run("build_collector_v1_blocked_cell_remediation_foundation.py", args.strict)
    if build_code != 0:
        print("Blocked-cell remediation foundation build failed; certification was not run.")
        return build_code

    certification_code = run("certify_collector_v1_blocked_cell_remediation_foundation.py", args.strict)
    if certification_code != 0:
        print("Blocked-cell remediation foundation certification failed.")
        return certification_code

    print("PASS_COLLECTOR_V1_BLOCKED_CELL_REMEDIATION_FOUNDATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
