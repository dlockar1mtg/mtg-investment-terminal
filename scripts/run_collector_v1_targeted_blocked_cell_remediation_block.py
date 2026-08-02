from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, strict: bool) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script)]
    if strict:
        cmd.append("--strict")
    completed = subprocess.run(cmd, cwd=ROOT)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    build_code = run("run_collector_v1_targeted_blocked_cell_remediation.py", args.strict)
    if build_code != 0:
        print("Targeted blocked-cell remediation build failed; certification was not run.")
        return build_code

    cert_code = run("certify_collector_v1_targeted_blocked_cell_remediation.py", args.strict)
    if cert_code != 0:
        print("Targeted blocked-cell remediation certification failed.")
        return cert_code

    print("PASS_COLLECTOR_V1_TARGETED_BLOCKED_CELL_REMEDIATION_BLOCK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
